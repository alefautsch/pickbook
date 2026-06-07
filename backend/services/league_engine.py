"""League-centric engine wiring — reuses DraftState scoring without draft picks (§5.7, §9)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dynasty_draft.dynasty_score import DynastyRatingCurve, DynastyWeights
from dynasty_draft.healthy_ppg import HealthyPpgStore
from dynasty_draft.ktc_values import KtcStore
from dynasty_draft.projections import SleeperProjectionStore
from dynasty_draft.recommender import DraftState
from dynasty_draft.sleeper_client import SleeperClient
from dynasty_draft.trade_value_blend import TradeValueBlend
from dynasty_draft.worp_blend import WorpBlend
from dynasty_draft.war_data import POSITIONS, PlayerValue, WarData

from backend.db.models import League
from backend.services.league_context import LeagueScoringContext, build_league_scoring_context


class LeagueScoringState(DraftState):
    """DraftState subclass: anchor pool = full player universe; snapshots = rostered only."""

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
    ) -> None:
        self._roster_player_ids = roster_player_ids
        self._league_row = league_row
        self._scoring_context = build_league_scoring_context(league_row)

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
        self.worp_blend = WorpBlend.from_config(settings)

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
                war=war,
                sleeper_players=sleeper_players,
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
            )
        except Exception:
            self.healthy_ppg_store = None

    @property
    def scoring_context(self) -> LeagueScoringContext:
        return self._scoring_context

    def _universe_pool(self) -> list[tuple[str, PlayerValue]]:
        """Full fantasy player universe for fixed OVR anchors (§5.7) — not roster-scoped."""
        pool: list[tuple[str, PlayerValue]] = []
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
    if not war_path.exists():
        raise FileNotFoundError(f"Missing WAR file: {war_path}")

    client = client or SleeperClient()
    sleeper_players = client.get_players()

    return LeagueScoringState(
        league_row=league_row,
        roster_player_ids=roster_player_ids,
        user_id=user_id,
        settings=settings,
        war=WarData(war_path),
        sleeper_players=sleeper_players,
        client=client,
    )
