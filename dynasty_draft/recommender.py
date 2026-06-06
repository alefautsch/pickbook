from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dynasty_draft.strategy import DraftStrategy
from dynasty_draft.war_data import POSITIONS, PlayerValue, WarData, normalize_name


STARTER_COUNTS: dict[str, int] = {
    "QB": 1,
    "RB": 2,
    "WR": 2,
    "TE": 1,
    "FLEX": 1,
}


@dataclass
class DraftState:
    draft: dict[str, Any]
    picks: list[dict[str, Any]]
    league: dict[str, Any] | None
    user_id: str
    war: WarData
    sleeper_players: dict[str, dict[str, Any]]
    trade_weight: float = 0.45
    worp_weight: float = 0.55
    strategy: DraftStrategy = field(default_factory=DraftStrategy)
    league_users: list[dict[str, Any]] = field(default_factory=list)

    drafted_ids: set[str] = field(init=False)
    my_roster_id: int | None = field(init=False)
    my_slot: int | None = field(init=False)
    roster_positions: list[str] = field(init=False)

    def __post_init__(self) -> None:
        self.drafted_ids = {p["player_id"] for p in self.picks if p.get("player_id")}
        self.my_roster_id, self.my_slot = self._resolve_my_team()
        self.roster_positions = self._resolve_roster_positions()

    def _resolve_my_team(self) -> tuple[int | None, int | None]:
        draft_order = self.draft.get("draft_order") or {}
        slot_to_roster = self.draft.get("slot_to_roster_id") or {}
        my_slot = draft_order.get(self.user_id)
        if my_slot is None:
            for pick in self.picks:
                if pick.get("picked_by") == self.user_id:
                    my_slot = pick.get("draft_slot")
                    break
        if my_slot is None and self.strategy.is_vet_draft:
            my_slot = self.strategy.startup_slot
        elif my_slot is None and self.strategy.is_rookie_draft:
            my_slot = self.strategy.rookie_draft_slot
        if my_slot is None:
            return None, None
        roster_id = slot_to_roster.get(str(my_slot))
        return (int(roster_id) if roster_id is not None else None, int(my_slot))

    def _resolve_roster_positions(self) -> list[str]:
        if self.league and self.league.get("roster_positions"):
            return list(self.league["roster_positions"])
        settings = self.draft.get("settings") or {}
        positions: list[str] = []
        for pos in POSITIONS:
            count = int(settings.get(f"slots_{pos.lower()}", 0) or 0)
            positions.extend([pos] * count)
        flex = int(settings.get("slots_flex", 0) or 0)
        positions.extend(["FLEX"] * flex)
        return positions

    def my_picks(self) -> list[dict[str, Any]]:
        if self.my_roster_id is None:
            return [p for p in self.picks if p.get("picked_by") == self.user_id]
        return [p for p in self.picks if int(p.get("roster_id", -1)) == self.my_roster_id]

    def _teams(self) -> int:
        return int((self.draft.get("settings") or {}).get("teams", self.strategy.teams))

    def _rounds(self) -> int:
        return int((self.draft.get("settings") or {}).get("rounds", 20))

    def _pick_slot(self, pick_no: int) -> int:
        teams = self._teams()
        round_no = (pick_no - 1) // teams + 1
        pos_in_round = (pick_no - 1) % teams + 1
        draft_type = (self.draft.get("type") or "snake").lower()
        if draft_type == "snake" and round_no % 2 == 0:
            return teams - pos_in_round + 1
        return pos_in_round

    def is_superflex(self) -> bool:
        if any(pos == "SUPER_FLEX" for pos in self.roster_positions):
            return True
        scoring = (self.draft.get("metadata") or {}).get("scoring_type", "")
        return "2qb" in str(scoring).lower() or "super" in str(scoring).lower()

    def consecutive_pick_numbers(self, from_pick: int | None = None) -> list[int]:
        """Upcoming run of your picks with no other teams between (bookend pairs)."""
        if self.my_slot is None:
            return []
        total_picks = self._teams() * self._rounds()
        start = from_pick or len(self.picks) + 1
        streak: list[int] = []
        for pick_no in range(start, total_picks + 1):
            if self._pick_slot(pick_no) == self.my_slot:
                streak.append(pick_no)
            elif streak:
                break
        return streak

    def next_pick_info(self) -> dict[str, Any]:
        teams = self._teams()
        rounds = self._rounds()
        total_picks = teams * rounds
        pick_no = len(self.picks) + 1
        if pick_no > total_picks:
            return {
                "pick_no": None,
                "is_my_pick": False,
                "picks_until_mine": None,
                "total_picks": total_picks,
                "back_to_back": False,
                "consecutive_picks": [],
            }
        round_no = (pick_no - 1) // teams + 1
        slot = self._pick_slot(pick_no)
        is_my_pick = self.my_slot is not None and slot == self.my_slot
        picks_until = 0
        if self.my_slot is not None and not is_my_pick:
            for future_pick in range(pick_no, total_picks + 1):
                if self._pick_slot(future_pick) == self.my_slot:
                    picks_until = future_pick - pick_no
                    break
        consecutive = self.consecutive_pick_numbers(from_pick=pick_no if is_my_pick else pick_no + picks_until)
        return {
            "pick_no": pick_no,
            "round": round_no,
            "slot": slot,
            "is_my_pick": is_my_pick,
            "picks_until_mine": picks_until if not is_my_pick else 0,
            "total_picks": total_picks,
            "my_upcoming": self.strategy.snake_pick_numbers(rounds=6),
            "back_to_back": len(consecutive) >= 2,
            "consecutive_picks": consecutive,
        }

    def _sleeper_name(self, player_id: str) -> str | None:
        player = self.sleeper_players.get(player_id)
        if not player:
            return None
        return player.get("full_name") or f"{player.get('first_name', '')} {player.get('last_name', '')}".strip()

    def _is_rookie(self, player_id: str) -> bool:
        player = self.sleeper_players.get(player_id) or {}
        years_exp = player.get("years_exp")
        if years_exp is not None:
            return int(years_exp) == 0
        name = player.get("full_name") or ""
        war_player = self.war.lookup(name)
        return war_player is not None and war_player.worp is None

    def _match_war(self, player_id: str) -> PlayerValue | None:
        name = self._sleeper_name(player_id)
        if not name:
            return None
        return self.war.lookup(name)

    def available_players(self) -> list[tuple[str, PlayerValue]]:
        reserved_names = {normalize_name(name) for name in self.strategy.reserved_rookies}
        available: list[tuple[str, PlayerValue]] = []
        for player_id, sleeper_player in self.sleeper_players.items():
            if player_id in self.drafted_ids:
                continue
            pos = (sleeper_player.get("position") or "").upper()
            if pos not in POSITIONS:
                continue
            name = sleeper_player.get("full_name") or ""
            war_player = self.war.lookup(name)
            if war_player is None:
                continue
            if war_player.trade_value <= 0:
                continue
            is_rookie = self._is_rookie(player_id)
            if self.strategy.is_vet_draft and is_rookie:
                continue
            if self.strategy.is_rookie_draft and not is_rookie:
                continue
            if self.strategy.is_rookie_draft and normalize_name(name) in reserved_names:
                continue
            available.append((player_id, war_player))
        return available

    def roster_counts(self) -> dict[str, int]:
        counts = {pos: 0 for pos in POSITIONS}
        counts["FLEX"] = 0
        for pick in self.my_picks():
            meta = pick.get("metadata") or {}
            pos = (meta.get("position") or "").upper()
            if pos in counts:
                counts[pos] += 1
        if self.strategy.is_vet_draft:
            for pos, reserved_count in self.strategy.reserved_by_position(self.war).items():
                counts[pos] += reserved_count
        return counts

    def starter_needs(self) -> dict[str, int]:
        counts = self.roster_counts()
        needs: dict[str, int] = {}
        qb_slots = sum(1 for p in self.roster_positions if p == "QB")
        superflex_slots = sum(1 for p in self.roster_positions if p == "SUPER_FLEX")
        needs["QB"] = max(0, qb_slots + superflex_slots - counts.get("QB", 0))
        for pos in ("RB", "WR", "TE"):
            roster_need = sum(1 for p in self.roster_positions if p == pos)
            needs[pos] = max(0, roster_need - counts.get(pos, 0))
        flex_slots = sum(1 for p in self.roster_positions if p == "FLEX")
        skill = counts["RB"] + counts["WR"] + counts["TE"]
        base_skill = sum(1 for p in self.roster_positions if p in {"RB", "WR", "TE"})
        needs["FLEX"] = max(0, flex_slots - max(0, skill - base_skill))
        return needs

    def _normalize_scores(self, available: list[tuple[str, PlayerValue]]) -> dict[str, float]:
        trade_vals = [p.trade_value for _, p in available]
        worps = [p.worp for _, p in available if p.worp is not None]
        max_tv = max(trade_vals) if trade_vals else 1.0
        max_worp = max(worps) if worps else 1.0
        scores: dict[str, float] = {}
        for player_id, player in available:
            tv_norm = player.trade_value / max_tv if max_tv else 0.0
            if player.worp is not None and max_worp:
                worp_norm = max(player.worp, 0) / max_worp
            else:
                worp_norm = tv_norm * 0.85
            upside_norm = player.upside
            base = self.trade_weight * tv_norm + self.worp_weight * worp_norm + 0.08 * upside_norm
            scores[player_id] = base
        return scores

    def _replacement_levels(
        self, scores: dict[str, float], available: list[tuple[str, PlayerValue]]
    ) -> dict[str, float]:
        by_pos: dict[str, list[float]] = {pos: [] for pos in POSITIONS}
        for player_id, player in available:
            by_pos[player.pos].append(scores[player_id])
        levels: dict[str, float] = {}
        teams = int((self.draft.get("settings") or {}).get("teams", self.strategy.teams))
        for pos in POSITIONS:
            ranked = sorted(by_pos[pos], reverse=True)
            if not ranked:
                levels[pos] = 0.0
                continue
            idx = min(len(ranked) - 1, teams - 1)
            levels[pos] = ranked[idx]
        return levels

    def _position_adjustments(self, round_no: int) -> dict[str, float]:
        need_weights = {"QB": 0.12, "RB": 0.10, "WR": 0.08, "TE": 0.14, "FLEX": 0.05}
        penalties: dict[str, float] = {pos: 0.0 for pos in POSITIONS}

        if self.is_superflex():
            need_weights["QB"] = 0.18
            need_weights["WR"] = 0.09

        if self.strategy.is_vet_draft:
            reserved = self.strategy.reserved_by_position(self.war)
            if reserved.get("RB", 0) > 0:
                need_weights["RB"] = 0.03
                if round_no <= 5:
                    penalties["RB"] = 0.14
                elif round_no <= 8:
                    penalties["RB"] = 0.06
                need_weights["WR"] = max(need_weights["WR"], 0.11)
                need_weights["QB"] = max(need_weights["QB"], 0.15)
                need_weights["TE"] = 0.15

        if self.strategy.is_rookie_draft:
            need_weights["RB"] = 0.02
            penalties["RB"] = 0.0

        return {"need_weights": need_weights, "penalties": penalties}

    def _scored_recommendations(self) -> list[dict[str, Any]]:
        available = self.available_players()
        if not available:
            return []
        base_scores = self._normalize_scores(available)
        replacement = self._replacement_levels(base_scores, available)
        needs = self.starter_needs()
        round_no = int(self.next_pick_info().get("round") or 1)
        adjustments = self._position_adjustments(round_no)
        need_weights: dict[str, float] = adjustments["need_weights"]
        penalties: dict[str, float] = adjustments["penalties"]

        recommendations: list[dict[str, Any]] = []
        for player_id, player in available:
            pos = player.pos
            vor = base_scores[player_id] - replacement.get(pos, 0.0)
            need_boost = needs.get(pos, 0) * need_weights.get(pos, 0.05)
            if pos in ("RB", "WR", "TE") and needs.get("FLEX", 0) > 0:
                need_boost += 0.03
            tier_bonus = 0.04 if player.worp_tier is not None and player.worp_tier <= 1 else 0.0
            penalty = penalties.get(pos, 0.0)
            final = vor + need_boost + tier_bonus - penalty
            note = ""
            if penalty > 0 and pos == "RB":
                note = "RB deprioritized (Jeremiyah Love reserved)"
            recommendations.append(
                {
                    "player_id": player_id,
                    "name": player.name,
                    "pos": pos,
                    "team": player.team,
                    "trade_value": player.trade_value,
                    "worp": player.worp,
                    "worp_tier": player.worp_tier,
                    "score": final,
                    "vor": vor,
                    "need_boost": need_boost,
                    "note": note,
                }
            )
        recommendations.sort(key=lambda row: row["score"], reverse=True)
        return recommendations

    def recommend(self, limit: int = 15) -> list[dict[str, Any]]:
        return self._scored_recommendations()[:limit]

    def recommend_by_position(self, per_pos: int = 12) -> dict[str, list[dict[str, Any]]]:
        by_pos: dict[str, list[dict[str, Any]]] = {pos: [] for pos in POSITIONS}
        for row in self._scored_recommendations():
            by_pos[row["pos"]].append(row)
        return {pos: rows[:per_pos] for pos, rows in by_pos.items()}

    def roster_summary(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for pick in sorted(self.my_picks(), key=lambda p: p.get("pick_no", 0)):
            player_id = pick.get("player_id")
            war_player = self._match_war(player_id) if player_id else None
            meta = pick.get("metadata") or {}
            rows.append(
                {
                    "pick_no": pick.get("pick_no"),
                    "round": pick.get("round"),
                    "name": war_player.name if war_player else self._sleeper_name(player_id or "") or "Unknown",
                    "pos": meta.get("position") or (war_player.pos if war_player else ""),
                    "trade_value": war_player.trade_value if war_player else None,
                    "worp": war_player.worp if war_player else None,
                    "status": "drafted",
                }
            )
        if self.strategy.is_vet_draft:
            for reserved in self.strategy.reserved_players(self.war):
                rows.append(
                    {
                        "pick_no": None,
                        "round": "R",
                        "name": reserved["name"],
                        "pos": reserved["pos"],
                        "trade_value": reserved["trade_value"],
                        "worp": None,
                        "status": "reserved (rookie draft)",
                    }
                )
        return rows

    def tier_cliffs(self, top_n: int = 5) -> list[dict[str, Any]]:
        available = sorted(self.available_players(), key=lambda item: item[1].trade_value, reverse=True)
        cliffs: list[dict[str, Any]] = []
        for pos in POSITIONS:
            pos_players = [p for _, p in available if p.pos == pos][:top_n + 1]
            for idx in range(len(pos_players) - 1):
                gap = pos_players[idx].trade_value - pos_players[idx + 1].trade_value
                if gap >= 400:
                    cliffs.append(
                        {
                            "pos": pos,
                            "player": pos_players[idx].name,
                            "next": pos_players[idx + 1].name,
                            "gap": gap,
                        }
                    )
                    break
        return cliffs
