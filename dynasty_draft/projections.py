from __future__ import annotations

import json
import time
from typing import Any

from dynasty_draft.sleeper_client import CACHE_DIR, SleeperClient
from dynasty_draft.war_data import POSITIONS, WarData, normalize_name

PROJECTIONS_TTL_SECONDS = 6 * 60 * 60
_DEFAULT_WORP_PER_VOR = 0.012


def _projections_cache_path(season: str) -> Any:
    return CACHE_DIR / f"sleeper_projections_{season}.json"


def _pts_field(ppr: float) -> str:
    if ppr >= 1.0:
        return "pts_ppr"
    if ppr >= 0.5:
        return "pts_half_ppr"
    return "pts_std"


def _replacement_index(
    pos: str,
    *,
    teams: int,
    roster_positions: list[str],
    superflex: bool,
) -> int:
    qb_slots = sum(1 for slot in roster_positions if slot == "QB")
    sf_slots = sum(1 for slot in roster_positions if slot == "SUPER_FLEX")
    rb_slots = sum(1 for slot in roster_positions if slot == "RB")
    wr_slots = sum(1 for slot in roster_positions if slot == "WR")
    te_slots = sum(1 for slot in roster_positions if slot == "TE")
    flex_slots = sum(1 for slot in roster_positions if slot == "FLEX")

    if pos == "QB":
        starters = teams * qb_slots
        if superflex:
            starters += int(teams * sf_slots * 0.85)
        return max(0, starters - 1)
    if pos == "RB":
        return max(0, teams * rb_slots + int(teams * flex_slots * 0.40) - 1)
    if pos == "WR":
        return max(0, teams * wr_slots + int(teams * flex_slots * 0.45) - 1)
    if pos == "TE":
        return max(0, teams * te_slots + int(teams * flex_slots * 0.15) - 1)
    return max(0, teams - 1)


class SleeperProjectionStore:
    """Sleeper season projections → VOR → WORP-scale win-now value."""

    def __init__(
        self,
        *,
        season: str,
        teams: int,
        roster_positions: list[str],
        superflex: bool,
        ppr: float = 0.5,
        war: WarData | None = None,
        sleeper_players: dict[str, dict[str, Any]] | None = None,
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.season = season
        self.teams = teams
        self.roster_positions = roster_positions
        self.superflex = superflex
        self.ppr = ppr
        self._pts_field = _pts_field(ppr)
        self._by_player_id: dict[str, float] = {}
        self._vor_by_player_id: dict[str, float] = {}
        self._worp_by_player_id: dict[str, float] = {}
        self._replacement_pts: dict[str, float] = {}
        self._worp_per_vor: dict[str, float] = {pos: _DEFAULT_WORP_PER_VOR for pos in POSITIONS}

        if rows is not None:
            self._ingest_rows(rows)
        if war is not None and sleeper_players is not None:
            self._calibrate_worp_scale(war, sleeper_players)

    @classmethod
    def load(
        cls,
        client: SleeperClient,
        *,
        season: str,
        teams: int,
        roster_positions: list[str],
        superflex: bool,
        ppr: float,
        war: WarData,
        sleeper_players: dict[str, dict[str, Any]],
        force_refresh: bool = False,
    ) -> SleeperProjectionStore:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = _projections_cache_path(season)
        rows: list[dict[str, Any]] | None = None
        if (
            not force_refresh
            and cache_path.exists()
            and (time.time() - cache_path.stat().st_mtime) < PROJECTIONS_TTL_SECONDS
        ):
            rows = json.loads(cache_path.read_text(encoding="utf-8"))

        if rows is None:
            positions_query = "&".join(f"position[]={pos}" for pos in POSITIONS)
            path = (
                f"https://api.sleeper.com/projections/nfl/{season}"
                f"?season_type=regular&{positions_query}&order_by=pts_ppr"
            )
            response = client.session.get(path, timeout=90)
            response.raise_for_status()
            rows = response.json()
            cache_path.write_text(json.dumps(rows), encoding="utf-8")

        return cls(
            season=season,
            teams=teams,
            roster_positions=roster_positions,
            superflex=superflex,
            ppr=ppr,
            war=war,
            sleeper_players=sleeper_players,
            rows=rows,
        )

    def _ingest_rows(self, rows: list[dict[str, Any]]) -> None:
        by_pos: dict[str, list[tuple[str, float]]] = {pos: [] for pos in POSITIONS}
        for row in rows:
            player_id = row.get("player_id")
            player = row.get("player") or {}
            pos = (player.get("position") or "").upper()
            if not player_id or pos not in POSITIONS:
                continue
            stats = row.get("stats") or {}
            pts = stats.get(self._pts_field) or stats.get("pts_ppr")
            if pts is None:
                continue
            points = float(pts)
            self._by_player_id[str(player_id)] = points
            by_pos[pos].append((str(player_id), points))

        for pos in POSITIONS:
            ranked = sorted(by_pos[pos], key=lambda item: item[1], reverse=True)
            if not ranked:
                continue
            idx = _replacement_index(
                pos,
                teams=self.teams,
                roster_positions=self.roster_positions,
                superflex=self.superflex,
            )
            idx = min(idx, len(ranked) - 1)
            self._replacement_pts[pos] = ranked[idx][1]
            for player_id, points in ranked:
                self._vor_by_player_id[player_id] = points - self._replacement_pts[pos]

    def _calibrate_worp_scale(self, war: WarData, sleeper_players: dict[str, dict[str, Any]]) -> None:
        ratios_by_pos: dict[str, list[float]] = {pos: [] for pos in POSITIONS}
        for player_id, vor in self._vor_by_player_id.items():
            if vor <= 0:
                continue
            sleeper = sleeper_players.get(player_id) or {}
            name = sleeper.get("full_name") or ""
            war_player = war.lookup(name)
            if war_player is None or war_player.worp is None or war_player.worp < 0.2:
                continue
            pos = war_player.pos
            if pos in ratios_by_pos:
                ratios_by_pos[pos].append(war_player.worp / vor)

        for pos in POSITIONS:
            ratios = sorted(ratios_by_pos[pos])
            if ratios:
                self._worp_per_vor[pos] = ratios[len(ratios) // 2]
            scale = self._worp_per_vor[pos]
            for player_id, vor in self._vor_by_player_id.items():
                sleeper = sleeper_players.get(player_id) or {}
                if (sleeper.get("position") or "").upper() != pos:
                    continue
                self._worp_by_player_id[player_id] = max(0.0, vor * scale)

    def replacement_ppg(self, pos: str) -> float:
        """League replacement rate per active week (season pts ÷ 17)."""
        season = self._replacement_pts.get(pos)
        if season is None:
            return 0.0
        return float(season) / 17.0

    def worp_per_vor(self, pos: str) -> float:
        return float(self._worp_per_vor.get(pos, _DEFAULT_WORP_PER_VOR))

    def projected_points(self, player_id: str | None) -> float | None:
        if not player_id:
            return None
        return self._by_player_id.get(str(player_id))

    def projected_vor(self, player_id: str | None, pos: str) -> float | None:
        if not player_id:
            return None
        return self._vor_by_player_id.get(str(player_id))

    def projected_worp(self, player_id: str | None, pos: str) -> float | None:
        if not player_id:
            return None
        cached = self._worp_by_player_id.get(str(player_id))
        if cached is not None:
            return cached
        vor = self.projected_vor(player_id, pos)
        if vor is None:
            return None
        return max(0.0, vor * self._worp_per_vor.get(pos, _DEFAULT_WORP_PER_VOR))

    def lookup_player_id(self, name: str, sleeper_players: dict[str, dict[str, Any]]) -> str | None:
        key = normalize_name(name)
        for player_id, player in sleeper_players.items():
            if normalize_name(player.get("full_name") or "") == key:
                return str(player_id)
        return None
