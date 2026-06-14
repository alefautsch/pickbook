"""Trade calculator — exposes evaluate_trade_package and dual-side LLM validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.settings import _read_settings
from backend.config import get_settings
from backend.db.models import League, PlayerSnapshot, Roster, RosterPlayer
from backend.schemas.trade import (
    TradeEvaluateRequest,
    TradeEvaluation,
    TradeEvaluateResponse,
    TradeLineupImpact,
    TradeLineupSide,
    TradeLineupStarterSlot,
    TradeResolvedSide,
    TradeSideValidation,
    TradeValidationResult,
)
from backend.services.advisor_tools import AdvisorToolContext, AdvisorTools, evaluate_trade_package
from backend.services.analysis_service import _player_row_from_snapshot
from backend.services.league_context import build_league_scoring_context
from backend.services.read_service import get_team_detail
from backend.services.trade_engine import evaluate_trade_lineup_deltas
from backend.services.trade_validation_service import (
    build_validation_payload,
    validate_trade_with_llm,
    _fairness_label_for_counterparty,
)
from dynasty_draft.war_data import WarData


def _tv_fairness_grade(eval_result: dict[str, Any]) -> str:
    pct = abs(float(eval_result.get("net_delta_adjusted_pct") or 0))
    if eval_result.get("within_band"):
        return "A"
    if pct <= 8:
        return "B+"
    if pct <= 14:
        return "B"
    if pct <= 22:
        return "C+"
    if pct <= 30:
        return "C"
    if pct <= 40:
        return "D"
    return "F"


def _accept_likelihood_grade(likelihood: str | None) -> str:
    key = str(likelihood or "medium").lower()
    return {
        "high": "A",
        "medium": "B",
        "low": "D",
    }.get(key, "C")


def _overall_grade(tv_grade: str, side_a_grade: str | None, side_b_grade: str | None) -> str:
    order = ["F", "D", "C", "C+", "B", "B+", "A"]
    tv_idx = order.index(tv_grade) if tv_grade in order else 3
    grades = [g for g in (side_a_grade, side_b_grade) if g]
    if not grades:
        return tv_grade
    accept_idx = min(order.index(g) if g in order else 3 for g in grades)
    combined = min(tv_idx, accept_idx)
    return order[combined]


def _favors_roster_id(
    fairness: str,
    *,
    side_a_roster_id: str,
    side_b_roster_id: str,
) -> str | None:
    if fairness == "fair":
        return None
    if fairness == "favors_you":
        return side_a_roster_id
    return side_b_roster_id


def _make_tools(db: Session, league_id: str, proposer_roster_id: str) -> AdvisorTools:
    my_roster = db.scalar(
        select(Roster).where(Roster.league_id == league_id, Roster.is_me.is_(True))
    )
    my_roster_id = str(my_roster.sleeper_roster_id) if my_roster else proposer_roster_id
    return AdvisorTools(
        AdvisorToolContext(
            db=db,
            league_id=league_id,
            my_roster_id=my_roster_id,
            focused_roster_id=proposer_roster_id,
        )
    )


def _trade_inputs(req: TradeEvaluateRequest) -> tuple[dict[str, Any], dict[str, Any]]:
    give = {
        "players": list(req.side_a_gives.players),
        "picks": [p.model_dump() for p in req.side_a_gives.picks],
    }
    receive = {
        "players": list(req.side_b_gives.players),
        "picks": [p.model_dump() for p in req.side_b_gives.picks],
    }
    return give, receive


def _to_resolved_side(data: dict[str, Any]) -> TradeResolvedSide:
    return TradeResolvedSide(
        players=data.get("players") or [],
        picks=data.get("picks") or [],
    )


def _load_roster_lineup_players(
    db: Session,
    league_id: str,
    roster_id: str,
    *,
    snapshots: dict[str, PlayerSnapshot],
    war: WarData,
) -> list[dict[str, Any]]:
    roster = db.scalar(
        select(Roster).where(
            Roster.league_id == league_id,
            Roster.sleeper_roster_id == roster_id,
        )
    )
    if roster is None:
        return []
    player_ids = db.scalars(
        select(RosterPlayer.sleeper_player_id).where(RosterPlayer.roster_id == roster.id)
    ).all()
    rows: list[dict[str, Any]] = []
    for player_id in player_ids:
        snap = snapshots.get(player_id)
        if snap is not None:
            rows.append(_player_row_from_snapshot(snap, war))
    return rows


def _lineup_players_for_ids(
    player_ids: list[str],
    snapshots: dict[str, PlayerSnapshot],
    war: WarData,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for player_id in player_ids:
        snap = snapshots.get(player_id)
        if snap is not None:
            rows.append(_player_row_from_snapshot(snap, war))
    return rows


def _compute_lineup_impact(
    db: Session,
    league_id: str,
    req: TradeEvaluateRequest,
    *,
    give: dict[str, Any],
    receive: dict[str, Any],
    eval_result: dict[str, Any],
) -> TradeLineupImpact | None:
    if eval_result.get("missing_assets"):
        return None
    give_ids = list(give.get("players") or [])
    recv_ids = list(receive.get("players") or [])
    give_picks = list(give.get("picks") or [])
    recv_picks = list(receive.get("picks") or [])
    if not give_ids and not recv_ids and not give_picks and not recv_picks:
        return None

    league_row = db.get(League, league_id)
    if league_row is None:
        return None
    roster_positions = build_league_scoring_context(league_row).roster_positions

    user_settings = _read_settings(db)
    war = WarData(Path(str(user_settings.get("war_csv") or "war.csv")))
    snapshots = {
        row.sleeper_player_id: row
        for row in db.scalars(
            select(PlayerSnapshot).where(PlayerSnapshot.league_id == league_id)
        ).all()
    }

    side_a_roster = _load_roster_lineup_players(
        db,
        league_id,
        req.side_a_roster_id,
        snapshots=snapshots,
        war=war,
    )
    side_b_roster = _load_roster_lineup_players(
        db,
        league_id,
        req.side_b_roster_id,
        snapshots=snapshots,
        war=war,
    )
    give_players = _lineup_players_for_ids(give_ids, snapshots, war)
    receive_players = _lineup_players_for_ids(recv_ids, snapshots, war)

    resolved_give = eval_result.get("give") or {}
    resolved_recv = eval_result.get("receive") or {}

    deltas = evaluate_trade_lineup_deltas(
        side_a_roster,
        side_b_roster,
        give_players=give_players,
        receive_players=receive_players,
        roster_positions=roster_positions,
        side_a_incoming_player_ids=set(recv_ids),
        side_b_incoming_player_ids=set(give_ids),
        side_a_incoming_picks=resolved_recv.get("picks") or [],
        side_b_incoming_picks=resolved_give.get("picks") or [],
    )

    def _to_side(data: dict[str, Any]) -> TradeLineupSide:
        return TradeLineupSide(
            before=data.get("before"),
            after=data.get("after"),
            delta=data.get("delta"),
            starters=[TradeLineupStarterSlot(**slot) for slot in data.get("starters") or []],
            incoming_picks=data.get("incoming_picks") or [],
        )

    return TradeLineupImpact(
        side_a=_to_side(deltas["side_a"]),
        side_b=_to_side(deltas["side_b"]),
    )


def _build_evaluation(
    eval_result: dict[str, Any],
    *,
    side_a_roster_id: str,
    side_b_roster_id: str,
    lineup: TradeLineupImpact | None = None,
) -> TradeEvaluation:
    fairness = str(eval_result.get("fairness") or "fair")
    return TradeEvaluation(
        give_total_tv=float(eval_result.get("give_total_tv") or 0),
        receive_total_tv=float(eval_result.get("receive_total_tv") or 0),
        give_value_adjustment=float(eval_result.get("give_value_adjustment") or 0),
        receive_value_adjustment=float(eval_result.get("receive_value_adjustment") or 0),
        give_adjusted_tv=float(eval_result.get("give_adjusted_tv") or 0),
        receive_adjusted_tv=float(eval_result.get("receive_adjusted_tv") or 0),
        give_effective_tv=float(eval_result.get("give_effective_tv") or 0),
        receive_effective_tv=float(eval_result.get("receive_effective_tv") or 0),
        consolidation_tax_tv=float(eval_result.get("consolidation_tax_tv") or 0),
        consolidation_premium_pct=int(eval_result.get("consolidation_premium_pct") or 12),
        give_consolidating=bool(eval_result.get("give_consolidating")),
        receive_consolidating=bool(eval_result.get("receive_consolidating")),
        net_delta_tv=float(eval_result.get("net_delta_tv") or 0),
        net_delta_adjusted_tv=float(eval_result.get("net_delta_adjusted_tv") or 0),
        net_delta_effective_tv=float(eval_result.get("net_delta_effective_tv") or 0),
        net_delta_adjusted_total_tv=float(eval_result.get("net_delta_adjusted_total_tv") or 0),
        net_delta_pct=float(eval_result.get("net_delta_pct") or 0),
        net_delta_adjusted_pct=float(eval_result.get("net_delta_adjusted_pct") or 0),
        fairness_band=str(eval_result.get("fairness_band") or "±5%"),
        within_band=bool(eval_result.get("within_band")),
        fairness=fairness,  # type: ignore[arg-type]
        positional_notes=list(eval_result.get("positional_notes") or []),
        missing_assets=list(eval_result.get("missing_assets") or []),
        give=_to_resolved_side(eval_result.get("give") or {}),
        receive=_to_resolved_side(eval_result.get("receive") or {}),
        tv_fairness_grade=_tv_fairness_grade(eval_result),
        favors_roster_id=_favors_roster_id(
            fairness,
            side_a_roster_id=side_a_roster_id,
            side_b_roster_id=side_b_roster_id,
        ),
        lineup=lineup,
    )


def evaluate_trade(
    db: Session,
    league_id: str,
    req: TradeEvaluateRequest,
) -> TradeEvaluateResponse | None:
    tools = _make_tools(db, league_id, req.side_a_roster_id)
    give, receive = _trade_inputs(req)
    eval_result = evaluate_trade_package(
        give,
        receive,
        resolve_player=tools._resolve_player,
        resolve_pick=tools._resolve_pick,
    )
    team_a = get_team_detail(db, league_id, req.side_a_roster_id)
    team_b = get_team_detail(db, league_id, req.side_b_roster_id)
    if team_a is None or team_b is None:
        return None
    lineup = _compute_lineup_impact(
        db,
        league_id,
        req,
        give=give,
        receive=receive,
        eval_result=eval_result,
    )
    return TradeEvaluateResponse(
        side_a_roster_id=req.side_a_roster_id,
        side_b_roster_id=req.side_b_roster_id,
        side_a_team_name=team_a.team_name,
        side_b_team_name=team_b.team_name,
        evaluation=_build_evaluation(
            eval_result,
            side_a_roster_id=req.side_a_roster_id,
            side_b_roster_id=req.side_b_roster_id,
            lineup=lineup,
        ),
    )


def _lineup_side_dict(side: TradeLineupSide | None) -> dict[str, Any] | None:
    if side is None:
        return None
    return side.model_dump()


def _run_side_validation(
    tools: AdvisorTools,
    *,
    proposer_roster_id: str,
    counterparty_roster_id: str,
    give: dict[str, Any],
    receive: dict[str, Any],
    eval_result: dict[str, Any],
    api_key: str | None,
    proposer_lineup: dict[str, Any] | None = None,
    counterparty_lineup: dict[str, Any] | None = None,
    tv_fairness_grade: str | None = None,
) -> TradeSideValidation:
    proposer_team = tools.get_team(proposer_roster_id)
    counterparty_team = tools.get_team(counterparty_roster_id)
    if proposer_team.get("error") or counterparty_team.get("error"):
        return TradeSideValidation(
            roster_id=counterparty_roster_id,
            team_name=counterparty_team.get("team_name"),
            view_mode="accept_if_offered",
            skipped=True,
            error=str(counterparty_team.get("error") or proposer_team.get("error")),
        )

    tv_ctx = dict(eval_result)
    if tv_fairness_grade:
        tv_ctx["tv_fairness_grade"] = tv_fairness_grade

    payload = build_validation_payload(
        proposer_roster_id=proposer_roster_id,
        counterparty_roster_id=counterparty_roster_id,
        proposer_team=proposer_team,
        counterparty_team=counterparty_team,
        give=eval_result["give"],
        receive=eval_result["receive"],
        tv_evaluation=tv_ctx,
        proposer_lineup=proposer_lineup,
        counterparty_lineup=counterparty_lineup,
    )
    validation = validate_trade_with_llm(payload, api_key=api_key)
    if validation.get("skipped"):
        return TradeSideValidation(
            roster_id=counterparty_roster_id,
            team_name=counterparty_team.get("team_name"),
            view_mode="accept_if_offered",
            skipped=True,
            error=str(validation.get("reason") or "AI validation unavailable"),
        )
    if validation.get("error"):
        return TradeSideValidation(
            roster_id=counterparty_roster_id,
            team_name=counterparty_team.get("team_name"),
            view_mode="accept_if_offered",
            skipped=True,
            error=str(validation.get("error")),
        )

    likelihood = validation.get("accept_likelihood")
    fairness = validation.get("fairness_from_counterparty_view")
    return TradeSideValidation(
        roster_id=counterparty_roster_id,
        team_name=counterparty_team.get("team_name"),
        view_mode="accept_if_offered",
        accept_likelihood=likelihood,
        fairness_view=fairness,
        fairness_label=_fairness_label_for_counterparty(
            fairness,
            counterparty_name=str(counterparty_team.get("team_name") or ""),
            proposer_name=str(proposer_team.get("team_name") or ""),
        ),
        would_improve_roster=validation.get("would_improve_their_roster"),
        reasoning=validation.get("reasoning"),
        blockers=list(validation.get("blockers") or []),
        suggested_tweak=validation.get("suggested_tweak"),
        grade=_accept_likelihood_grade(likelihood),
    )


def validate_trade_dual(
    db: Session,
    league_id: str,
    req: TradeEvaluateRequest,
) -> TradeValidationResult | None:
    tools_a = _make_tools(db, league_id, req.side_a_roster_id)
    give, receive = _trade_inputs(req)
    eval_result = evaluate_trade_package(
        give,
        receive,
        resolve_player=tools_a._resolve_player,
        resolve_pick=tools_a._resolve_pick,
    )
    team_a = get_team_detail(db, league_id, req.side_a_roster_id)
    team_b = get_team_detail(db, league_id, req.side_b_roster_id)
    if team_a is None or team_b is None:
        return None

    evaluation = _build_evaluation(
        eval_result,
        side_a_roster_id=req.side_a_roster_id,
        side_b_roster_id=req.side_b_roster_id,
        lineup=_compute_lineup_impact(
            db,
            league_id,
            req,
            give=give,
            receive=receive,
            eval_result=eval_result,
        ),
    )
    if eval_result.get("missing_assets"):
        return TradeValidationResult(
            evaluation=evaluation,
            side_a=TradeSideValidation(
                roster_id=req.side_a_roster_id,
                team_name=team_a.team_name,
                view_mode="accept_if_offered",
                skipped=True,
                error="Could not resolve all trade assets",
            ),
            side_b=TradeSideValidation(
                roster_id=req.side_b_roster_id,
                team_name=team_b.team_name,
                view_mode="accept_if_offered",
                skipped=True,
                error="Could not resolve all trade assets",
            ),
            overall_grade=evaluation.tv_fairness_grade,
            summary="Fix missing assets before AI evaluation.",
        )

    settings = get_settings()
    api_key = settings.anthropic_api_key

    tools_b = _make_tools(db, league_id, req.side_b_roster_id)

    lineup_a = _lineup_side_dict(evaluation.lineup.side_a) if evaluation.lineup else None
    lineup_b = _lineup_side_dict(evaluation.lineup.side_b) if evaluation.lineup else None

    side_b_validation = _run_side_validation(
        tools_a,
        proposer_roster_id=req.side_a_roster_id,
        counterparty_roster_id=req.side_b_roster_id,
        give=give,
        receive=receive,
        eval_result=eval_result,
        api_key=api_key,
        proposer_lineup=lineup_a,
        counterparty_lineup=lineup_b,
        tv_fairness_grade=evaluation.tv_fairness_grade,
    )
    side_b_validation.roster_id = req.side_b_roster_id
    side_b_validation.team_name = team_b.team_name

    flipped_eval = evaluate_trade_package(
        receive,
        give,
        resolve_player=tools_b._resolve_player,
        resolve_pick=tools_b._resolve_pick,
    )
    side_a_validation = _run_side_validation(
        tools_b,
        proposer_roster_id=req.side_b_roster_id,
        counterparty_roster_id=req.side_a_roster_id,
        give=receive,
        receive=give,
        eval_result=flipped_eval,
        api_key=api_key,
        proposer_lineup=lineup_b,
        counterparty_lineup=lineup_a,
        tv_fairness_grade=evaluation.tv_fairness_grade,
    )
    side_a_validation.roster_id = req.side_a_roster_id
    side_a_validation.team_name = team_a.team_name

    overall = _overall_grade(
        evaluation.tv_fairness_grade,
        side_a_validation.grade,
        side_b_validation.grade,
    )
    summary = _build_summary(
        evaluation=evaluation,
        side_a=side_a_validation,
        side_b=side_b_validation,
        side_a_name=team_a.team_name,
        side_b_name=team_b.team_name,
        overall_grade=overall,
    )
    return TradeValidationResult(
        evaluation=evaluation,
        side_a=side_a_validation,
        side_b=side_b_validation,
        overall_grade=overall,
        summary=summary,
    )


def _build_summary(
    *,
    evaluation: TradeEvaluation,
    side_a: TradeSideValidation,
    side_b: TradeSideValidation,
    side_a_name: str | None,
    side_b_name: str | None,
    overall_grade: str,
) -> str:
    a_label = side_a_name or "Side A"
    b_label = side_b_name or "Side B"
    parts = [
        f"Overall grade {overall_grade} — TV fairness {evaluation.tv_fairness_grade} "
        f"({evaluation.net_delta_adjusted_pct:+.1f}% adjusted delta).",
    ]
    if evaluation.lineup:
        a_delta = evaluation.lineup.side_a.delta
        b_delta = evaluation.lineup.side_b.delta
        if a_delta is not None and b_delta is not None:
            parts.append(
                f"Starter PPG delta: {a_label} {a_delta:+.1f} / {b_label} {b_delta:+.1f}."
            )
    if not side_a.skipped and side_a.accept_likelihood:
        parts.append(
            f"{a_label} would likely {side_a.accept_likelihood} accept (grade {side_a.grade})."
        )
    if not side_b.skipped and side_b.accept_likelihood:
        parts.append(
            f"{b_label} would likely {side_b.accept_likelihood} accept (grade {side_b.grade})."
        )
    if evaluation.within_band:
        parts.append("Package is within the ±5% fairness band.")
    return " ".join(parts)
