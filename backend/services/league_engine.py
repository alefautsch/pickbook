"""League-centric engine wiring — reuses DraftState scoring without draft picks (§5.7, §9)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from dynasty_draft.dynasty_score import DynastyRatingCurve, DynastyWeights
from dynasty_draft.dynasty_dealer import load_dynasty_dealer_store
from dynasty_draft.healthy_ppg import HealthyPpgStore
from dynasty_draft.ktc_values import KtcStore
from dynasty_draft.projections import SleeperProjectionStore
from dynasty_draft.recommender import DraftState
from dynasty_draft.sleeper_client import SleeperClient
from dynasty_draft.scoring_adjustments import tep_adjusted_trade_value
from dynasty_draft.trade_value_blend import TradeValueBlend
from dynasty_draft.worp_blend import WorpBlend
from dynasty_draft.player_identity import sleeper_identity_score
from dynasty_draft.war_loader import load_war_data
from dynasty_draft.war_data import POSITIONS, PlayerValue, WarData, normalize_name

from backend.db.models import League
from backend.services.league_context import LeagueScoringContext, build_league_scoring_context


class LeagueScoringState(DraftState):
    """DraftState subclass: anchor pool = full universe; snapshots = rostered + top-N FAs."""

    def __init__(
        self,
        *,
        league_row: League,
        roster_player_ids: set[str],
        user_id: str,
        settings: dict[str, Any],
        war: WarData,
        sleeper_players: dict[str, dict[str, Any]],
        client: SleeperClient,
        war_load_meta: dict[str, Any] | None = None,
    ) -> None:
        self._roster_player_ids = roster_player_ids
        self._league_row = league_row
        self._scoring_context = build_league_scoring_context(league_row)
        self._war_load_meta = war_load_meta or {}

        league_dict = {
            "league_id": league_row.sleeper_league_id,
            "name": league_row.name,
            "season": league_row.season,
            "total_rosters": league_row.total_rosters,
            "roster_positions": league_row.roster_positions_json,
            "scoring_settings": league_row.scoring_json,
        }
        fake_draft = {
            "settings": {"teams": league_row.total_rosters, "rounds": 1},
            "type": "snake",
            "draft_order": {},
            "slot_to_roster_id": {},
        }

        super().__init__(
            draft=fake_draft,
            picks=[],
            league=league_dict,
            user_id=user_id,
            war=war,
            sleeper_players=sleeper_players,
            trade_weight=float(settings.get("trade_weight", 0.65)),
            worp_weight=float(settings.get("worp_weight", 0.35)),
            dynasty_weights=DynastyWeights.from_config(settings.get("dynasty_weights")),
            dynasty_rating_curve=DynastyRatingCurve.from_config(settings.get("dynasty_rating_curve")),
        )

        self.ktc = None
        if settings.get("ktc_enabled", True):
            try:
                self.ktc = KtcStore.load(superflex=self.is_superflex())
            except Exception:
                self.ktc = None
        self.trade_blend = TradeValueBlend.from_config(
            settings, ktc_available=self.ktc is not None
        )
        self.dealer = load_dynasty_dealer_store(
            settings,
            superflex=self.is_superflex(),
            force_refresh=bool(settings.get("_force_metric_refresh")),
        )
        self.worp_blend = WorpBlend.from_config(settings)
        force_metric_refresh = bool(settings.get("_force_metric_refresh"))

        scoring = self._scoring_context
        season = str(settings.get("season", league_row.season))
        try:
            self.projection_store = SleeperProjectionStore.load(
                client,
                season=season,
                teams=scoring.team_count,
                roster_positions=scoring.roster_positions,
                superflex=scoring.superflex,
                ppr=scoring.ppr,
                te_premium=scoring.te_premium,
                war=war,
                sleeper_players=sleeper_players,
                force_refresh=force_metric_refresh,
            )
        except Exception:
            self.projection_store = None

        try:
            self.healthy_ppg_store = HealthyPpgStore.load(
                sleeper_players=sleeper_players,
                war=war,
                teams=scoring.team_count,
                roster_positions=scoring.roster_positions,
                superflex=scoring.superflex,
                ppr=scoring.ppr,
                te_premium=scoring.te_premium,
                force_refresh=force_metric_refresh,
            )
        except Exception:
            self.healthy_ppg_store = None

    @property
    def scoring_context(self) -> LeagueScoringContext:
        return self._scoring_context

    def blended_trade_value(self, player: PlayerValue, *, player_id: str | None = None) -> float:
        return self.with_blended_tv(player, player_id=player_id).trade_value

    def with_blended_tv(self, player: PlayerValue, *, player_id: str | None = None) -> PlayerValue:
        blended = super().with_blended_tv(player, player_id=player_id)
        if player.pos != "TE" or self._scoring_context.te_premium <= 0:
            return blended
        store = getattr(self, "healthy_ppg_store", None)
        row = store.lookup(None, name=player.name) if store is not None else None
        if row is None:
            return blended
        adjusted_tv = tep_adjusted_trade_value(
            blended.trade_value,
            position=player.pos,
            te_premium=self._scoring_context.te_premium,
            hppg=row.healthy_ppg,
            receptions_per_game=row.receptions_per_game,
        )
        if adjusted_tv == blended.trade_value:
            return blended
        return replace(blended, trade_value=adjusted_tv)

    def _universe_pool(self) -> list[tuple[str, PlayerValue]]:
        """Full fantasy player universe for fixed OVR anchors (§5.7) — not roster-scoped."""
        pool: list[tuple[str, PlayerValue]] = []
        for player_id, sleeper_player in self.sleeper_players.items():
            pos = (sleeper_player.get("position") or "").upper()
            if pos not in POSITIONS:
                continue
            war_player = self._match_war(str(player_id))
            if war_player is None:
                continue
            if self.blended_trade_value(war_player) <= 0:
                continue
            pool.append((str(player_id), war_player))
        return pool

    def _dynasty_reference_pool(self) -> list[tuple[str, PlayerValue]]:
        """Fixed anchors from the full player universe — ignores who is rostered (§5.7)."""
        return self._universe_pool()

    def scoring_pool(self) -> list[tuple[str, PlayerValue]]:
        """Players to snapshot — rostered in this league only (§14.2)."""
        pool: list[tuple[str, PlayerValue]] = []
        for player_id in sorted(self._roster_player_ids):
            war_player = self._match_war(player_id)
            if war_player is None:
                continue
            pos = (war_player.pos or "").upper()
            if pos not in POSITIONS:
                continue
            if self.blended_trade_value(war_player) <= 0:
                continue
            pool.append((player_id, war_player))
        return pool

    def fa_scoring_pool(self, top_n: int = 150) -> list[tuple[str, PlayerValue]]:
        """Top-N unrostered players by blended TV — snapshotted at sync (§14.2 Phase 3)."""
        best_by_name: dict[str, tuple[str, PlayerValue, float, int]] = {}
        for player_id, war_player in self._universe_pool():
            if player_id in self._roster_player_ids:
                continue
            name_key = normalize_name(war_player.name)
            tv = self.blended_trade_value(war_player)
            identity = sleeper_identity_score(self, player_id, war_player)
            prev = best_by_name.get(name_key)
            if prev is None or identity > prev[3] or (identity == prev[3] and tv > prev[2]):
                best_by_name[name_key] = (player_id, war_player, tv, identity)
        candidates = sorted(best_by_name.values(), key=lambda row: row[2], reverse=True)
        return [(player_id, war_player) for player_id, war_player, _, _ in candidates[:top_n]]

    def snapshot_pool(self, fa_top_n: int = 150) -> list[tuple[str, PlayerValue]]:
        """Rostered + FA pool for player_snapshots (deduped, roster wins)."""
        seen: set[str] = set()
        pool: list[tuple[str, PlayerValue]] = []
        for player_id, war_player in self.scoring_pool():
            seen.add(player_id)
            pool.append((player_id, war_player))
        for player_id, war_player in self.fa_scoring_pool(fa_top_n):
            if player_id in seen:
                continue
            seen.add(player_id)
            pool.append((player_id, war_player))
        return pool

    def flex_pool(self) -> list[tuple[str, PlayerValue]]:
        return [
            (pid, player)
            for pid, player in self.scoring_pool()
            if player.pos in {"RB", "WR", "TE"}
        ]


def build_league_scoring_state(
    *,
    league_row: League,
    roster_player_ids: set[str],
    user_id: str,
    settings: dict[str, Any],
    client: SleeperClient | None = None,
) -> LeagueScoringState:
    war_path = Path(str(settings.get("war_csv", "war.csv")))
    if not war_path.exists() and not bool((settings.get("dynasty_daddy") or {}).get("enabled", True)):
        raise FileNotFoundError(f"Missing WAR file: {war_path}")

    client = client or SleeperClient()
    sleeper_players = client.get_players()

    war, war_meta = load_war_data(
        settings,
        league_row=league_row,
        force_refresh=bool(settings.get("_force_metric_refresh")),
    )

    return LeagueScoringState(
        league_row=league_row,
        roster_player_ids=roster_player_ids,
        user_id=user_id,
        settings=settings,
        war=war,
        sleeper_players=sleeper_players,
        client=client,
        war_load_meta=war_meta,
    )
