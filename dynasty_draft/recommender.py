from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dynasty_draft.adp import AdpIndex
from dynasty_draft.external_adp import AdpStore
from dynasty_draft.dynasty_score import (
    DynastyRatingCurve,
    DynastyReferenceAnchors,
    DynastyScorer,
    DynastyWeights,
    PerGameAnchorMaxes,
    compute_per_game_anchor_maxes,
    compute_reference_anchors,
    curved_composite_to_rating,
)
from dynasty_draft.draft_pick_ownership import PickOwnerIndex, resolve_pick_owner
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

FLEX_ELIGIBLE = frozenset({"RB", "WR", "TE"})

# Value-based drafting: cross-position surplus + ADP fall bonus; penalize reaches.
VALUE_OVERRIDE_ADP_DELTA = 6
ADP_VALUE_PER_PICK = 0.012
ADP_VALUE_CAP = 0.25
ADP_REACH_PER_PICK = 0.015
ADP_REACH_PENALTY_CAP = 0.35
WAIT_FOR_UPCOMING_WINDOW = 4
WAIT_FOR_UPCOMING_PENALTY = 0.22
BPA_VOR_WEIGHT = 0.55
BPA_DYNASTY_WEIGHT = 0.45


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
    dynasty_rating_curve: DynastyRatingCurve | None = None
    projection_store: SleeperProjectionStore | None = None
    healthy_ppg_store: Any | None = None
    ktc: KtcStore | None = None
    adp_store: AdpStore | None = None
    trade_blend: TradeValueBlend = field(default_factory=TradeValueBlend)
    worp_blend: WorpBlend = field(default_factory=WorpBlend)
    strategy: DraftStrategy = field(default_factory=DraftStrategy)
    league_users: list[dict[str, Any]] = field(default_factory=list)
    pick_owner_index: PickOwnerIndex = field(default_factory=dict)
    pick_no_owner_index: dict[int, int] = field(default_factory=dict)
    roster_owner_ids: dict[int, str] = field(default_factory=dict)

    drafted_ids: set[str] = field(init=False)
    drafted_names: set[str] = field(init=False)
    my_roster_id: int | None = field(init=False)
    my_slot: int | None = field(init=False)
    roster_positions: list[str] = field(init=False)

    def __post_init__(self) -> None:
        drafted_ids: set[str] = set()
        drafted_names: set[str] = set()
        for pick in self.picks:
            player_id = pick.get("player_id")
            if player_id:
                pid = str(player_id)
                drafted_ids.add(pid)
                war_player = self._match_war(pid)
                if war_player:
                    drafted_names.add(normalize_name(war_player.name))
            meta = pick.get("metadata") or {}
            meta_name = " ".join(
                part
                for part in (meta.get("first_name"), meta.get("last_name"))
                if part
            ).strip()
            if meta_name:
                drafted_names.add(normalize_name(meta_name))
        self.drafted_ids = drafted_ids
        self.drafted_names = drafted_names
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

    def _draft_season(self) -> str:
        if self.draft.get("season") is not None:
            return str(self.draft["season"])
        if self.league and self.league.get("season") is not None:
            return str(self.league["season"])
        return ""

    def original_roster_for_slot(self, slot: int) -> int | None:
        roster_id = (self.draft.get("slot_to_roster_id") or {}).get(str(slot))
        return int(roster_id) if roster_id is not None else None

    def owner_roster_for_pick(self, pick_no: int) -> int | None:
        if self.pick_no_owner_index:
            owner = self.pick_no_owner_index.get(pick_no)
            if owner is not None:
                return owner
        slot = self._pick_slot(pick_no)
        original = self.original_roster_for_slot(slot)
        if original is None:
            return None
        season = self._draft_season()
        if not season:
            return original
        if not self.pick_owner_index:
            return original
        teams = self._teams()
        round_no = (pick_no - 1) // teams + 1
        return resolve_pick_owner(
            self.pick_owner_index,
            season=season,
            round_no=round_no,
            original_roster_id=original,
        )

    def user_id_for_roster(self, roster_id: int) -> str | None:
        uid = self.roster_owner_ids.get(int(roster_id))
        if uid:
            return uid
        draft_order = self.draft.get("draft_order") or {}
        slot_to_roster = self.draft.get("slot_to_roster_id") or {}
        for user_id, slot in draft_order.items():
            rid = slot_to_roster.get(str(slot))
            if rid is not None and int(rid) == int(roster_id):
                return str(user_id)
        return None

    def is_my_pick_number(self, pick_no: int) -> bool:
        if self.my_roster_id is None:
            return False
        owner = self.owner_roster_for_pick(pick_no)
        return owner is not None and owner == self.my_roster_id

    def is_superflex(self) -> bool:
        if any(pos == "SUPER_FLEX" for pos in self.roster_positions):
            return True
        scoring = (self.draft.get("metadata") or {}).get("scoring_type", "")
        return "2qb" in str(scoring).lower() or "super" in str(scoring).lower()

    def consecutive_pick_numbers(self, from_pick: int | None = None) -> list[int]:
        """Upcoming run of your picks with no other teams between (bookend pairs)."""
        if self.my_roster_id is None:
            return []
        total_picks = self._teams() * self._rounds()
        start = from_pick or len(self.picks) + 1
        streak: list[int] = []
        for pick_no in range(start, total_picks + 1):
            if self.is_my_pick_number(pick_no):
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
        is_my_pick = self.is_my_pick_number(pick_no)
        picks_until = 0
        if self.my_roster_id is not None and not is_my_pick:
            for future_pick in range(pick_no, total_picks + 1):
                if self.is_my_pick_number(future_pick):
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
        player = self.sleeper_players.get(str(player_id))
        if not player:
            return None
        return player.get("full_name") or f"{player.get('first_name', '')} {player.get('last_name', '')}".strip()

    def _is_rookie(self, player_id: str) -> bool:
        player = self.sleeper_players.get(str(player_id)) or {}
        years_exp = player.get("years_exp")
        if years_exp is not None:
            return int(years_exp) == 0
        name = player.get("full_name") or ""
        war_player = self.war.lookup(name)
        return war_player is not None and war_player.worp is None

    def _match_war(self, player_id: str) -> PlayerValue | None:
        sleeper = self.sleeper_players.get(player_id) or {}
        name = self._sleeper_name(player_id)
        if not name:
            return None
        war_player = self.war.lookup(name)
        if war_player is None:
            return None
        sleeper_pos = (sleeper.get("position") or "").upper()
        if sleeper_pos and war_player.pos and sleeper_pos != war_player.pos:
            return None
        return war_player

    def ktc_value(self, name: str) -> int | None:
        if self.ktc is None or not name:
            return None
        return self.ktc.lookup(name)

    def blended_trade_value(self, player: PlayerValue) -> float:
        blended = self.trade_blend.blend(player.trade_value, self.ktc_value(player.name))
        return blended if blended is not None else player.trade_value

    def with_blended_tv(self, player: PlayerValue) -> PlayerValue:
        return self.trade_blend.apply(player, self.ktc_value(player.name))

    def value_inputs(self, player: PlayerValue, blended: PlayerValue | None = None) -> dict[str, Any]:
        ktc = self.ktc_value(player.name)
        blended_value = (blended or self.with_blended_tv(player)).trade_value
        inputs = self.war.lookup_value_inputs(player.name)
        inputs["ktc"] = {
            "enabled": self.ktc is not None,
            "trade_value": ktc,
            "format": "superflex" if self.is_superflex() else "standard",
        }
        inputs["blend"] = {
            "dd_weight": self.trade_blend.dd_weight,
            "ktc_weight": self.trade_blend.ktc_weight,
            "dd_trade_value": player.trade_value,
            "ktc_trade_value": ktc,
            "trade_value": blended_value,
        }
        return inputs

    def blend_pool(self, pool: list[tuple[str, PlayerValue]]) -> list[tuple[str, PlayerValue]]:
        return [(player_id, self.with_blended_tv(player)) for player_id, player in pool]

    def _eligible_players(self) -> list[tuple[str, PlayerValue]]:
        """Full draft-eligible board (ignores who has been picked)."""
        eligible: list[tuple[str, PlayerValue]] = []
        for player_id, sleeper_player in self.sleeper_players.items():
            pos = (sleeper_player.get("position") or "").upper()
            if pos not in POSITIONS:
                continue
            war_player = self._match_war(str(player_id))
            if war_player is None:
                continue
            if self.blended_trade_value(war_player) <= 0:
                continue
            is_rookie = self._is_rookie(player_id)
            if self.strategy.is_vet_draft and is_rookie:
                continue
            if self.strategy.is_rookie_draft and not is_rookie:
                continue
            eligible.append((player_id, war_player))
        return eligible

    def _dynasty_reference_pool(self) -> list[tuple[str, PlayerValue]]:
        """Pre-draft eligible board — OVR anchors stay fixed as picks are made."""
        return self._eligible_players()

    def _dynasty_per_game_reference(self) -> PerGameAnchorMaxes:
        """Fixed board maxes for per-game OVR normalization (QB vs flex pool)."""
        if getattr(self, "_dynasty_per_game_ref_ready", False):
            return self._dynasty_per_game_anchors
        ref_pool = self._dynasty_reference_pool()
        per_game = self._per_game_by_id_for_pool(ref_pool) or {}
        pos_by_id = {player_id: player.pos for player_id, player in ref_pool}
        self._dynasty_per_game_anchors = compute_per_game_anchor_maxes(per_game, pos_by_id)
        self._dynasty_per_game_ref_ready = True
        return self._dynasty_per_game_anchors

    def _pos_by_id_for_pool(self, pool: list[tuple[str, PlayerValue]]) -> dict[str, str]:
        return {player_id: player.pos for player_id, player in pool}

    def _dynasty_curve_context(self) -> tuple[DynastyReferenceAnchors, tuple[float, float]]:
        if getattr(self, "_dynasty_curve_ready", False):
            return self._dynasty_ref_anchors, self._dynasty_rating_bounds
        ref_pool = self.blend_pool(self._dynasty_reference_pool())
        anchors = compute_reference_anchors(ref_pool, self._effective_worp)
        ids = [player_id for player_id, _ in ref_pool]
        per_game_max = self._dynasty_per_game_reference()
        raw_scores = self._dynasty_scorer().score_pool(
            ref_pool,
            age_by_id={pid: self._player_age(pid) for pid in ids},
            years_exp_by_id={pid: self._years_exp(pid) for pid in ids},
            effective_worp=self._effective_worp,
            reference=anchors,
            rating_bounds=None,
            per_game_by_id=self._per_game_by_id_for_pool(ref_pool),
            per_game_max=per_game_max,
            pos_by_id=self._pos_by_id_for_pool(ref_pool),
        )
        composites = [row["dynasty_score"] for row in raw_scores.values()]
        bounds = (min(composites), max(composites)) if composites else (0.0, 1.0)
        self._dynasty_ref_anchors = anchors
        self._dynasty_rating_bounds = bounds
        self._dynasty_curve_ready = True
        return anchors, bounds

    def _dynasty_reference_anchors(self) -> DynastyReferenceAnchors:
        anchors, _ = self._dynasty_curve_context()
        return anchors

    def available_players(self) -> list[tuple[str, PlayerValue]]:
        return [
            (player_id, player)
            for player_id, player in self._eligible_players()
            if str(player_id) not in self.drafted_ids
            and normalize_name(player.name) not in self.drafted_names
        ]

    def roster_counts(self) -> dict[str, int]:
        counts = {pos: 0 for pos in POSITIONS}
        counts["FLEX"] = 0
        for pick in self.my_picks():
            meta = pick.get("metadata") or {}
            pos = (meta.get("position") or "").upper()
            if pos in counts:
                counts[pos] += 1
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
            cached = WorpProjector(
                self.war,
                self.projection_store,
                self.worp_blend,
                getattr(self, "healthy_ppg_store", None),
            )
            self._cached_worp_projector = cached
        return cached

    def _adp_index(self) -> AdpIndex:
        cached = getattr(self, "_cached_adp_index", None)
        if cached is None:
            cached = AdpIndex(
                self.war,
                self.blended_trade_value,
                external=self.adp_store,
            )
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

    def _adp_bpa_adjustment(
        self,
        adp_pick: int | None,
        adp_delta: int | None,
        ref_pick: int | None,
    ) -> tuple[float, str, bool, bool]:
        """
        ADP adjustment for BPA scoring.
        Returns (adjustment, note, wait_for_later, value_override).
        """
        adjustment = 0.0
        notes: list[str] = []
        wait_for_later = False

        if adp_delta is not None:
            if adp_delta > 0:
                adjustment += min(ADP_VALUE_CAP, adp_delta * ADP_VALUE_PER_PICK)
                if adp_delta >= VALUE_OVERRIDE_ADP_DELTA:
                    notes.append(f"VBD value +{adp_delta} vs ADP")
            elif adp_delta < 0:
                reach = abs(adp_delta)
                adjustment -= min(ADP_REACH_PENALTY_CAP, reach * ADP_REACH_PER_PICK)
                if reach >= 6:
                    notes.append(f"Reach {reach} vs ADP")

        if adp_pick is not None and ref_pick is not None and adp_pick > ref_pick + 2:
            upcoming = self.next_pick_info().get("my_upcoming") or []
            for pick in upcoming:
                if pick <= ref_pick:
                    continue
                if abs(adp_pick - pick) <= WAIT_FOR_UPCOMING_WINDOW:
                    adjustment -= WAIT_FOR_UPCOMING_PENALTY
                    notes.append(f"ADP #{adp_pick} — wait for pick #{pick}")
                    wait_for_later = True
                    break

        value_override = (
            adp_delta is not None
            and adp_delta >= VALUE_OVERRIDE_ADP_DELTA
            and not wait_for_later
        )
        return adjustment, "; ".join(notes), wait_for_later, value_override

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
        if player.get("porp") is None and war_player.porp is not None:
            player["porp"] = war_player.porp
        healthy = self._healthy_ppg_metrics(
            str(player_id) if player_id else None,
            war_player,
            name=player.get("name"),
        )
        if healthy:
            player.update(healthy)
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
            cached = DynastyScorer(
                self.dynasty_weights,
                self.dynasty_rating_curve,
            )
            self._cached_dynasty_scorer = cached
        return cached

    def _per_game_by_id_for_pool(
        self,
        pool: list[tuple[str, PlayerValue]],
    ) -> dict[str, dict[str, float]] | None:
        result: dict[str, dict[str, float]] = {}
        for player_id, player in pool:
            metrics = self._healthy_ppg_metrics(player_id, player)
            if metrics:
                result[player_id] = metrics
        return result or None

    def dynasty_scores(
        self, players: list[tuple[str, PlayerValue]] | None = None
    ) -> dict[str, dict[str, Any]]:
        score_pool = self.blend_pool(players if players is not None else self.available_players())
        ids = [player_id for player_id, _ in score_pool]
        anchors, bounds = self._dynasty_curve_context()
        return self._dynasty_scorer().score_pool(
            score_pool,
            age_by_id={pid: self._player_age(pid) for pid in ids},
            years_exp_by_id={pid: self._years_exp(pid) for pid in ids},
            effective_worp=self._effective_worp,
            reference=anchors,
            rating_bounds=bounds,
            per_game_by_id=self._per_game_by_id_for_pool(score_pool),
            per_game_max=self._dynasty_per_game_reference(),
            pos_by_id=self._pos_by_id_for_pool(score_pool),
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
                    "porp": player.porp,
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
        self.attach_flex_ratings(recommendations, self._available_flex_by_id())
        self.attach_healthy_metrics(recommendations)
        recommendations.sort(key=lambda row: row["score"], reverse=True)
        return recommendations

    def recommend(self, limit: int = 15) -> list[dict[str, Any]]:
        return self._scored_recommendations()[:limit]

    def bpa_recommendations(self, limit: int = 15) -> list[dict[str, Any]]:
        """Best player available: cross-position VOR + dynasty + ADP value; no need boost."""
        available = self.available_players()
        if not available:
            return []

        blended = self.blend_pool(available)
        base_scores = self._normalize_scores(available)
        replacement = self._replacement_levels(base_scores, available)
        adp = self._adp_index()
        ref_pick = self._adp_reference_pick()
        dynasty_by_id = self.dynasty_scores(available)

        rows: list[dict[str, Any]] = []
        for player_id, player in blended:
            pos = player.pos
            vor = base_scores[player_id] - replacement.get(pos, 0.0)
            dynasty = dynasty_by_id.get(player_id) or {}
            rating = dynasty.get("dynasty_rating") or 0
            dynasty_norm = (rating - 50) / 49.0 if rating else 0.0
            adp_pick = adp.pick_no(player.name)
            adp_delta = adp.delta(player.name, ref_pick) if ref_pick and adp_pick else None
            adp_adj, note, wait_for_later, value_override = self._adp_bpa_adjustment(
                adp_pick, adp_delta, ref_pick
            )
            bpa_score = BPA_VOR_WEIGHT * vor + BPA_DYNASTY_WEIGHT * dynasty_norm + adp_adj
            blended_player = self.with_blended_tv(player)
            eff_worp, worp_projected = self._effective_worp(player_id, blended_player)
            rows.append(
                {
                    "player_id": player_id,
                    "name": player.name,
                    "pos": pos,
                    "team": player.team,
                    "age": dynasty.get("age") or self._player_age(player_id),
                    "trade_value": self.blended_trade_value(player),
                    "worp": player.worp,
                    "porp": player.porp,
                    "effective_worp": eff_worp,
                    "worp_uses_projection": worp_projected,
                    "projected_worp": eff_worp if worp_projected else None,
                    "worp_tier": player.worp_tier,
                    "adp_pick": adp_pick,
                    "adp_delta": adp_delta,
                    "adp_class": adp.adp_class(adp_delta),
                    "dynasty_score": dynasty.get("dynasty_score"),
                    "dynasty_rating": rating,
                    "dynasty_rookie": dynasty.get("dynasty_rookie"),
                    "dynasty_components": dynasty.get("dynasty_components"),
                    "vor": vor,
                    "bpa_score": bpa_score,
                    "adp_adjustment": adp_adj,
                    "value_override": value_override,
                    "wait_for_later": wait_for_later,
                    "note": note,
                }
            )
        self.attach_flex_ratings(rows, self._available_flex_by_id())
        self.attach_healthy_metrics(rows)
        rows.sort(key=lambda row: row["bpa_score"], reverse=True)
        return rows[:limit]

    def value_pivot_summary(self, limit: int = 8) -> dict[str, Any]:
        """Where BPA disagrees with need-adjusted ranking — take value, trade surplus."""
        scan = max(limit * 2, 16)
        bpa = self.bpa_recommendations(limit=scan)
        need = self.recommend(limit=scan)
        bpa_rank = {row["name"]: index + 1 for index, row in enumerate(bpa)}
        need_rank = {row["name"]: index + 1 for index, row in enumerate(need)}

        take_bpa: list[dict[str, Any]] = []
        wait_for_later: list[dict[str, Any]] = []
        for row in bpa:
            if row.get("wait_for_later"):
                wait_for_later.append(
                    {
                        "name": row["name"],
                        "pos": row["pos"],
                        "dynasty_rating": row.get("dynasty_rating"),
                        "adp_pick": row.get("adp_pick"),
                        "adp_delta": row.get("adp_delta"),
                        "reason": row.get("note"),
                    }
                )

        for row in bpa[:limit]:
            if row.get("wait_for_later"):
                continue
            adp_delta = row.get("adp_delta")
            if adp_delta is not None and adp_delta < -5:
                continue
            name = row["name"]
            bpa_pos = bpa_rank[name]
            need_pos = need_rank.get(name, 99)
            if row.get("value_override") or (bpa_pos <= 5 and need_pos >= 8) or (bpa_pos <= 3 and need_pos >= 6):
                take_bpa.append(
                    {
                        "name": name,
                        "pos": row["pos"],
                        "dynasty_rating": row.get("dynasty_rating"),
                        "trade_value": row.get("trade_value"),
                        "adp_delta": row.get("adp_delta"),
                        "bpa_rank": bpa_pos,
                        "need_rank": need_pos,
                        "reason": row.get("note") or f"BPA #{bpa_pos} vs need #{need_pos}",
                    }
                )

        def _compact(row: dict[str, Any], rank: int) -> dict[str, Any]:
            return {
                "rank": rank,
                "name": row["name"],
                "pos": row["pos"],
                "dynasty_rating": row.get("dynasty_rating"),
                "trade_value": row.get("trade_value"),
                "adp_pick": row.get("adp_pick"),
                "adp_delta": row.get("adp_delta"),
                "adp_class": row.get("adp_class"),
                "wait_for_later": row.get("wait_for_later"),
            }

        return {
            "bpa_top": [_compact(row, index + 1) for index, row in enumerate(bpa[:limit])],
            "need_adjusted_top": [_compact(row, index + 1) for index, row in enumerate(need[:limit])],
            "take_bpa_over_need": take_bpa[:limit],
            "wait_for_later": wait_for_later[:limit],
            "value_override_adp_delta": VALUE_OVERRIDE_ADP_DELTA,
            "note": (
                "take_bpa_over_need = clear ADP value or BPA beats need-adjusted. "
                "wait_for_later = ADP aligns with a future pick — do not reach now."
            ),
        }

    def bpa_by_position(self, per_pos: int = 8) -> dict[str, list[dict[str, Any]]]:
        by_pos: dict[str, list[dict[str, Any]]] = {pos: [] for pos in POSITIONS}
        for row in self.bpa_recommendations(limit=per_pos * len(POSITIONS)):
            by_pos[row["pos"]].append(row)
        return {pos: rows[:per_pos] for pos, rows in by_pos.items()}

    def dynasty_recommendations(
        self,
        pool: list[tuple[str, PlayerValue]] | None = None,
        *,
        pick_no: int | None = None,
        limit: int = 15,
    ) -> list[dict[str, Any]]:
        """Rank a pool by dynasty_rating with starter-need nudges."""
        available = pool if pool is not None else self.available_players()
        if not available:
            return []

        blended = self.blend_pool(available)
        ref_pick = pick_no or self.next_pick_info().get("pick_no") or 1
        round_no = (int(ref_pick) - 1) // self._teams() + 1
        needs = self.starter_needs()
        adjustments = self._position_adjustments(round_no)
        need_weights: dict[str, float] = adjustments["need_weights"]
        penalties: dict[str, float] = adjustments["penalties"]
        adp = self._adp_index()
        dynasty_by_id = self.dynasty_scores(blended)

        rows: list[dict[str, Any]] = []
        for player_id, player in blended:
            dynasty = dynasty_by_id.get(player_id) or {}
            rating = dynasty.get("dynasty_rating") or 0
            dynasty_norm = (rating - 50) / 49.0 if rating else 0.0
            pos = player.pos
            need_boost = needs.get(pos, 0) * need_weights.get(pos, 0.05)
            if pos in ("RB", "WR", "TE") and needs.get("FLEX", 0) > 0:
                need_boost += 0.03
            penalty = penalties.get(pos, 0.0)
            final = dynasty_norm + need_boost - penalty
            blended_tv = self.blended_trade_value(player)
            eff_worp, worp_projected = self._effective_worp(player_id, self.with_blended_tv(player))
            adp_pick = adp.pick_no(player.name)
            adp_delta = adp.delta(player.name, int(ref_pick)) if adp_pick else None
            rows.append(
                {
                    "player_id": player_id,
                    "name": player.name,
                    "pos": pos,
                    "team": player.team,
                    "age": dynasty.get("age") or self._player_age(player_id),
                    "trade_value": blended_tv,
                    "porp": player.porp,
                    "effective_worp": eff_worp,
                    "worp_uses_projection": worp_projected,
                    "dynasty_score": dynasty.get("dynasty_score"),
                    "dynasty_rating": rating,
                    "dynasty_rookie": dynasty.get("dynasty_rookie"),
                    "adp_pick": adp_pick,
                    "adp_delta": adp_delta,
                    "adp_class": adp.adp_class(adp_delta),
                    "dynasty_rank_score": final,
                }
            )
        self.attach_flex_ratings(rows, self._available_flex_by_id())
        self.attach_healthy_metrics(rows)
        rows.sort(key=lambda row: row["dynasty_rank_score"], reverse=True)
        return rows[:limit]

    def recommend_by_position(self, per_pos: int = 12) -> dict[str, list[dict[str, Any]]]:
        by_pos: dict[str, list[dict[str, Any]]] = {pos: [] for pos in POSITIONS}
        for row in self._scored_recommendations():
            by_pos[row["pos"]].append(row)
        return {pos: rows[:per_pos] for pos, rows in by_pos.items()}

    def _resolve_sleeper_id(
        self,
        player_id: str | None,
        *,
        name: str | None = None,
    ) -> str | None:
        if player_id:
            return str(player_id)
        if not name:
            return None
        key = normalize_name(name)
        for sid, sleeper in self.sleeper_players.items():
            if normalize_name(sleeper.get("full_name") or "") == key:
                return str(sid)
        return None

    def _healthy_ppg_metrics(
        self,
        player_id: str | None,
        player: PlayerValue | None = None,
        *,
        name: str | None = None,
    ) -> dict[str, float | int | str | bool] | None:
        lookup_name = name or (player.name if player else None)
        store = getattr(self, "healthy_ppg_store", None)
        if store is not None:
            row = store.lookup(str(player_id) if player_id else None, name=lookup_name)
            if row is not None:
                return {
                    "healthy_ppg": row.healthy_ppg,
                    "worp_ppg": row.worp_ppg,
                    "availability": row.availability,
                    "healthy_games": row.healthy_games,
                    "total_games": row.total_games,
                    "receptions_per_game": row.receptions_per_game,
                    "ppg_source": "nflverse",
                    "hppg_expected": False,
                }
        return self._expected_ppg_metrics(
            player_id,
            player,
            name=lookup_name,
        )

    def _expected_ppg_metrics(
        self,
        player_id: str | None,
        player: PlayerValue | None,
        *,
        name: str | None = None,
    ) -> dict[str, float | int | str | bool] | None:
        """Sleeper season projection or TV/WORP imputation when nflverse history is missing."""
        if player is None and name:
            player = self.war.lookup(name)
        if player is None:
            return None

        pid = self._resolve_sleeper_id(player_id, name=name or player.name)
        projections: SleeperProjectionStore | None = getattr(self, "projection_store", None)
        source = "estimated"
        season_pts: float | None = None
        worp_ppg: float | None = None

        if projections is not None and pid:
            season_pts = projections.projected_points(pid)
            projected_worp = projections.projected_worp(pid, player.pos)
            if projected_worp is not None:
                worp_ppg = projected_worp / 17.0
            if season_pts is not None:
                source = "projected"

        blended = self.with_blended_tv(player)
        eff, _ = self._effective_worp(pid, blended)
        if eff is not None and worp_ppg is None:
            worp_ppg = eff / 17.0

        if season_pts is None:
            if worp_ppg is None:
                return None
            if projections is not None:
                rep = projections.replacement_ppg(player.pos)
                scale = projections.worp_per_vor(player.pos)
                vor_ppg = worp_ppg / scale if scale > 0 else 0.0
                season_pts = (rep + vor_ppg) * 17.0
            else:
                season_pts = max(worp_ppg * 17.0 * 6.0, 0.0)

        ppg = season_pts / 17.0
        if worp_ppg is None and eff is not None:
            worp_ppg = eff / 17.0

        return {
            "healthy_ppg": round(ppg, 2),
            "worp_ppg": round(worp_ppg, 4) if worp_ppg is not None else None,
            "availability": 1.0,
            "healthy_games": 17,
            "total_games": 17,
            "ppg_source": source,
            "hppg_expected": True,
        }

    def _flex_raw_score(self, player_id: str, player: PlayerValue) -> float:
        """Cross-position flex comparability: per-game WORP when available."""
        healthy = self._healthy_ppg_metrics(player_id, player)
        porp_bump = (player.porp or 0.0) / 250.0 / 17.0
        if healthy and healthy.get("worp_ppg"):
            return float(healthy["worp_ppg"]) + porp_bump
        blended = self.with_blended_tv(player)
        eff, _ = self._effective_worp(player_id, blended)
        if eff is not None:
            return eff / 17.0 + porp_bump
        return self.blended_trade_value(player) * 0.00005 / 17.0 + porp_bump

    def drafted_skill_pool(self) -> list[tuple[str, PlayerValue]]:
        pool: list[tuple[str, PlayerValue]] = []
        seen: set[str] = set()
        for pick in self.picks:
            player_id = pick.get("player_id")
            if not player_id:
                continue
            key = str(player_id)
            if key in seen:
                continue
            war_player = self._match_war(key)
            if war_player and war_player.pos in FLEX_ELIGIBLE:
                pool.append((key, war_player))
                seen.add(key)
        return pool

    def _available_flex_by_id(self) -> dict[str, dict[str, Any]]:
        cached = getattr(self, "_cached_available_flex_by_id", None)
        if cached is None:
            cached = self.flex_relative_ratings()
            self._cached_available_flex_by_id = cached
        return cached

    @staticmethod
    def attach_flex_ratings(
        rows: list[dict[str, Any]],
        flex_by_id: dict[str, dict[str, Any]],
    ) -> None:
        for row in rows:
            player_id = row.get("player_id")
            if not player_id:
                continue
            flex = flex_by_id.get(str(player_id)) or {}
            row["flex_rating"] = flex.get("flex_rating")
            row["flex_rank"] = flex.get("flex_rank")

    def attach_healthy_metrics(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            player_id = str(row["player_id"]) if row.get("player_id") else None
            name = row.get("name")
            war_player = None
            if player_id:
                war_player = self._match_war(player_id)
            if war_player is None and name:
                war_player = self.war.lookup(name)
            healthy = self._healthy_ppg_metrics(player_id, war_player, name=name)
            if healthy:
                row.update(healthy)

    def flex_relative_ratings(
        self,
        pool: list[tuple[str, PlayerValue]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """
        Rank RB/WR/TE on a shared 50–99 scale within the pool.

        For flex-spot decisions: skill positions compared head-to-head instead of
        vs position-specific replacement or dedicated roster slots.
        """
        if pool is None:
            pool = self.available_players()
        flex_pool = [(pid, p) for pid, p in self.blend_pool(pool) if p.pos in FLEX_ELIGIBLE]
        if not flex_pool:
            return {}

        raw_by_id = {
            player_id: self._flex_raw_score(player_id, player)
            for player_id, player in flex_pool
        }
        sorted_ids = sorted(raw_by_id, key=lambda pid: raw_by_id[pid], reverse=True)
        raw_vals = list(raw_by_id.values())
        raw_min, raw_max = min(raw_vals), max(raw_vals)
        exponent = (self.dynasty_rating_curve or DynastyRatingCurve()).exponent

        result: dict[str, dict[str, Any]] = {}
        for rank, player_id in enumerate(sorted_ids, start=1):
            raw = raw_by_id[player_id]
            if raw_max > raw_min:
                composite = (raw - raw_min) / (raw_max - raw_min)
            else:
                composite = 1.0
            result[player_id] = {
                "flex_rating": curved_composite_to_rating(
                    composite,
                    raw_min=0.0,
                    raw_max=1.0,
                    exponent=exponent,
                ),
                "flex_rank": rank,
                "flex_pool_size": len(sorted_ids),
            }
        return result

    def available_board_rows(self) -> list[dict[str, Any]]:
        """Undrafted players with metrics for sortable board view."""
        available = self.available_players()
        if not available:
            return []

        blended = self.blend_pool(available)
        dynasty_by_id = self.dynasty_scores(available)
        flex_by_id = self.flex_relative_ratings(available)
        adp = self._adp_index()
        ref_pick = self._adp_reference_pick()

        rows: list[dict[str, Any]] = []
        for player_id, player in blended:
            dynasty = dynasty_by_id.get(player_id) or {}
            flex = flex_by_id.get(player_id) or {}
            blended_player = self.with_blended_tv(player)
            eff_worp, worp_projected = self._effective_worp(player_id, blended_player)
            adp_pick = adp.pick_no(player.name)
            adp_delta = adp.delta(player.name, ref_pick) if ref_pick and adp_pick else None
            healthy = self._healthy_ppg_metrics(player_id, player)
            row_data: dict[str, Any] = {
                "player_id": player_id,
                "name": player.name,
                "pos": player.pos,
                "team": player.team,
                "age": dynasty.get("age") or self._player_age(player_id),
                "trade_value": round(self.blended_trade_value(player)),
                "worp": player.worp,
                "effective_worp": eff_worp,
                "worp_projected": worp_projected,
                "porp": player.porp,
                "dynasty_rating": dynasty.get("dynasty_rating"),
                "dynasty_rookie": bool(dynasty.get("dynasty_rookie")),
                "flex_rating": flex.get("flex_rating"),
                "flex_rank": flex.get("flex_rank"),
                "adp_pick": adp_pick,
                "adp_delta": adp_delta,
            }
            if healthy:
                row_data.update(healthy)
            rows.append(row_data)
        return rows

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
                    "porp": war_player.porp if war_player else None,
                    "status": "drafted",
                }
            )
            if rows:
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
