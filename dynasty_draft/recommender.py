from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dynasty_draft.adp import AdpIndex
from dynasty_draft.dynasty_score import (
    DynastyReferenceAnchors,
    DynastyScorer,
    DynastyWeights,
    compute_reference_anchors,
)
from dynasty_draft.strategy import DraftStrategy
from dynasty_draft.war_data import POSITIONS, PlayerValue, WarData, normalize_name
from dynasty_draft.projections import SleeperProjectionStore
from dynasty_draft.ktc_values import KtcStore
from dynasty_draft.trade_value_blend import TradeValueBlend
from dynasty_draft.worp_blend import WorpBlend
from dynasty_draft.worp_projection import WorpProjector


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
    dynasty_weights: DynastyWeights | None = None
    projection_store: SleeperProjectionStore | None = None
    ktc: KtcStore | None = None
    trade_blend: TradeValueBlend = field(default_factory=TradeValueBlend)
    worp_blend: WorpBlend = field(default_factory=WorpBlend)
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

    def ktc_value(self, name: str) -> int | None:
        if self.ktc is None or not name:
            return None
        return self.ktc.lookup(name)

    def blended_trade_value(self, player: PlayerValue) -> float:
        blended = self.trade_blend.blend(player.trade_value, self.ktc_value(player.name))
        return blended if blended is not None else player.trade_value

    def with_blended_tv(self, player: PlayerValue) -> PlayerValue:
        return self.trade_blend.apply(player, self.ktc_value(player.name))

    def blend_pool(self, pool: list[tuple[str, PlayerValue]]) -> list[tuple[str, PlayerValue]]:
        return [(player_id, self.with_blended_tv(player)) for player_id, player in pool]

    def _eligible_players(self) -> list[tuple[str, PlayerValue]]:
        """Full draft-eligible board (ignores who has been picked)."""
        reserved_names = {normalize_name(name) for name in self.strategy.reserved_rookies}
        eligible: list[tuple[str, PlayerValue]] = []
        for player_id, sleeper_player in self.sleeper_players.items():
            pos = (sleeper_player.get("position") or "").upper()
            if pos not in POSITIONS:
                continue
            name = sleeper_player.get("full_name") or ""
            war_player = self.war.lookup(name)
            if war_player is None:
                continue
            if self.blended_trade_value(war_player) <= 0:
                continue
            is_rookie = self._is_rookie(player_id)
            if self.strategy.is_vet_draft and is_rookie:
                continue
            if self.strategy.is_rookie_draft and not is_rookie:
                continue
            if self.strategy.is_rookie_draft and normalize_name(name) in reserved_names:
                continue
            eligible.append((player_id, war_player))
        return eligible

    def _dynasty_reference_pool(self) -> list[tuple[str, PlayerValue]]:
        """Pre-draft eligible board — OVR anchors stay fixed as picks are made."""
        return self._eligible_players()

    def _dynasty_reference_anchors(self) -> DynastyReferenceAnchors:
        cached = getattr(self, "_dynasty_ref_anchors", None)
        if cached is not None:
            return cached
        ref_pool = self.blend_pool(self._dynasty_reference_pool())
        anchors = compute_reference_anchors(ref_pool, self._effective_worp)
        self._dynasty_ref_anchors = anchors
        return anchors

    def available_players(self) -> list[tuple[str, PlayerValue]]:
        return [
            (player_id, player)
            for player_id, player in self._eligible_players()
            if player_id not in self.drafted_ids
        ]

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

    def _worp_projector(self) -> WorpProjector:
        cached = getattr(self, "_cached_worp_projector", None)
        if cached is None:
            cached = WorpProjector(self.war, self.projection_store, self.worp_blend)
            self._cached_worp_projector = cached
        return cached

    def _adp_index(self) -> AdpIndex:
        cached = getattr(self, "_cached_adp_index", None)
        if cached is None:
            cached = AdpIndex(self.war, self.blended_trade_value)
            self._cached_adp_index = cached
        return cached

    def _adp_reference_pick(self) -> int | None:
        info = self.next_pick_info()
        if info.get("is_my_pick"):
            return info.get("pick_no")
        streak = info.get("consecutive_picks") or []
        if streak:
            return streak[0]
        pick_no = info.get("pick_no")
        until = info.get("picks_until_mine")
        if pick_no is not None and until is not None:
            return pick_no + until
        return pick_no

    def _years_exp(self, player_id: str) -> int | None:
        years_exp = self.sleeper_players.get(player_id, {}).get("years_exp")
        return int(years_exp) if years_exp is not None else None

    def _player_age(self, player_id: str) -> int | None:
        age = self.sleeper_players.get(player_id, {}).get("age")
        return int(age) if age is not None else None

    def _effective_worp(
        self,
        player_id: str | None,
        player: PlayerValue,
    ) -> tuple[float | None, bool]:
        pid = player_id or None
        return self._worp_projector().effective_worp(
            player,
            years_exp=self._years_exp(pid) if pid else None,
            player_id=pid,
        )

    def enrich_player_row(self, player: dict[str, Any]) -> None:
        """Attach age and blended effective_worp to a player row."""
        player_id = player.get("player_id")
        name = player.get("name")
        war_player = None
        if player_id:
            war_player = self._match_war(str(player_id))
        if war_player is None and name:
            war_player = self.war.lookup(name)
        if not player_id and name:
            key = normalize_name(name)
            for sid, sleeper in self.sleeper_players.items():
                if normalize_name(sleeper.get("full_name") or "") == key:
                    player_id = str(sid)
                    player["player_id"] = player_id
                    break
        if player_id and player.get("age") is None:
            age = self._player_age(str(player_id))
            if age is not None:
                player["age"] = age
        if war_player is None:
            return
        blended = self.with_blended_tv(war_player)
        eff, uses_projection = self._effective_worp(
            str(player_id) if player_id else None,
            blended,
        )
        if eff is not None:
            player["effective_worp"] = eff
            player["worp_uses_projection"] = uses_projection
            if uses_projection:
                player["projected_worp"] = eff

    def _dynasty_scorer(self) -> DynastyScorer:
        cached = getattr(self, "_cached_dynasty_scorer", None)
        if cached is None:
            cached = DynastyScorer(self.dynasty_weights)
            self._cached_dynasty_scorer = cached
        return cached

    def dynasty_scores(
        self, players: list[tuple[str, PlayerValue]] | None = None
    ) -> dict[str, dict[str, Any]]:
        score_pool = self.blend_pool(players if players is not None else self.available_players())
        ids = [player_id for player_id, _ in score_pool]
        return self._dynasty_scorer().score_pool(
            score_pool,
            age_by_id={pid: self._player_age(pid) for pid in ids},
            years_exp_by_id={pid: self._years_exp(pid) for pid in ids},
            effective_worp=self._effective_worp,
            reference=self._dynasty_reference_anchors(),
        )

    def _normalize_scores(self, available: list[tuple[str, PlayerValue]]) -> dict[str, float]:
        blended = self.blend_pool(available)
        trade_vals = [p.trade_value for _, p in blended]
        effective_worps: list[float] = []
        for player_id, player in blended:
            eff, _ = self._effective_worp(player_id, player)
            if eff is not None:
                effective_worps.append(max(eff, 0))
        max_tv = max(trade_vals) if trade_vals else 1.0
        max_worp = max(effective_worps) if effective_worps else 1.0
        scores: dict[str, float] = {}
        for player_id, player in blended:
            tv_norm = player.trade_value / max_tv if max_tv else 0.0
            eff, _ = self._effective_worp(player_id, player)
            if eff is not None and max_worp:
                worp_norm = max(eff, 0) / max_worp
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

        adp = self._adp_index()
        ref_pick = self._adp_reference_pick()
        dynasty_by_id = self.dynasty_scores(available)
        recommendations: list[dict[str, Any]] = []
        for player_id, player in available:
            blended_tv = self.blended_trade_value(player)
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
            blended_player = self.with_blended_tv(player)
            eff_worp, worp_projected = self._effective_worp(player_id, blended_player)
            adp_pick = adp.pick_no(player.name)
            adp_delta = adp.delta(player.name, ref_pick) if ref_pick and adp_pick else None
            dynasty = dynasty_by_id.get(player_id) or {}
            recommendations.append(
                {
                    "player_id": player_id,
                    "name": player.name,
                    "pos": pos,
                    "team": player.team,
                    "age": dynasty.get("age") or self._player_age(player_id),
                    "trade_value": blended_tv,
                    "worp": player.worp,
                    "effective_worp": eff_worp,
                    "worp_uses_projection": worp_projected,
                    "projected_worp": eff_worp if worp_projected else None,
                    "worp_tier": player.worp_tier,
                    "adp_pick": adp_pick,
                    "adp_delta": adp_delta,
                    "adp_class": adp.adp_class(adp_delta),
                    "dynasty_score": dynasty.get("dynasty_score"),
                    "dynasty_rating": dynasty.get("dynasty_rating"),
                    "dynasty_rookie": dynasty.get("dynasty_rookie"),
                    "dynasty_components": dynasty.get("dynasty_components"),
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
                    "trade_value": self.blended_trade_value(war_player) if war_player else None,
                    "worp": war_player.worp if war_player else None,
                    "status": "drafted",
                }
            )
            if rows:
                self.enrich_player_row(rows[-1])
        if self.strategy.is_vet_draft:
            for reserved in self.strategy.reserved_players(self.war, tv_fn=self.blended_trade_value):
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
                self.enrich_player_row(rows[-1])
        return rows

    def tier_cliffs(self, top_n: int = 5) -> list[dict[str, Any]]:
        available = sorted(
            self.available_players(),
            key=lambda item: self.blended_trade_value(item[1]),
            reverse=True,
        )
        cliffs: list[dict[str, Any]] = []
        for pos in POSITIONS:
            pos_players = [p for _, p in available if p.pos == pos][:top_n + 1]
            for idx in range(len(pos_players) - 1):
                gap = self.blended_trade_value(pos_players[idx]) - self.blended_trade_value(
                    pos_players[idx + 1]
                )
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
