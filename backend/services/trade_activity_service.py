"""Sync completed league trades from Sleeper and cache AI analysis."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import LeagueTransaction, PlayerSnapshot, Roster, RosterDraftPick
from backend.schemas.trade import TradeEvaluateRequest, TradePickRef, TradeSideInput, TradeSideValidation
from backend.schemas.trade_activity import (
    RecentTrade,
    RecentTradesResponse,
    TradeActivityAnalysis,
    TradeActivitySide,
)
from backend.services.trade_calculator_service import validate_trade_dual
from dynasty_draft.sleeper_client import SleeperClient

INITIAL_TRADE_BACKFILL = 10
INCREMENTAL_WEEK_LOOKBACK = 4
MAX_BACKFILL_WEEKS = 22


def _empty_side() -> dict[str, Any]:
    return {"gives": {"players": [], "picks": []}, "receives": {"players": [], "picks": []}}


def parse_trade_sides(txn: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map Sleeper transaction payload to per-roster give/receive assets."""
    roster_ids = [str(r) for r in txn.get("roster_ids") or []]
    sides = {rid: _empty_side() for rid in roster_ids}

    adds = txn.get("adds") or {}
    drops = txn.get("drops") or {}

    if drops:
        for player_id, rid in drops.items():
            rid = str(rid)
            if rid in sides:
                sides[rid]["gives"]["players"].append(str(player_id))
        for player_id, rid in adds.items():
            rid = str(rid)
            if rid in sides:
                sides[rid]["receives"]["players"].append(str(player_id))
    elif len(roster_ids) == 2:
        a, b = roster_ids
        for player_id, recv_rid in adds.items():
            recv_rid = str(recv_rid)
            pid = str(player_id)
            if recv_rid == a:
                sides[a]["receives"]["players"].append(pid)
                sides[b]["gives"]["players"].append(pid)
            elif recv_rid == b:
                sides[b]["receives"]["players"].append(pid)
                sides[a]["gives"]["players"].append(pid)
    else:
        for player_id, recv_rid in adds.items():
            rid = str(recv_rid)
            if rid in sides:
                sides[rid]["receives"]["players"].append(str(player_id))

    for pick in txn.get("draft_picks") or []:
        if not pick.get("season") or pick.get("round") is None:
            continue
        pick_ref = {
            "season": str(pick["season"]),
            "round": int(pick["round"]),
            "original_roster_id": str(pick.get("roster_id") or ""),
        }
        giver = str(pick.get("previous_owner_id") or "")
        receiver = str(pick.get("owner_id") or "")
        if giver in sides:
            sides[giver]["gives"]["picks"].append(pick_ref)
        if receiver in sides:
            sides[receiver]["receives"]["picks"].append(pick_ref)

    return sides


def _current_nfl_week(client: SleeperClient) -> int:
    try:
        state = client.get_nfl_state()
        week = int(state.get("week") or state.get("leg") or 0)
        # Offseason week=0 — scan full recent window for backfill/incremental.
        return week if week > 0 else MAX_BACKFILL_WEEKS
    except Exception:
        return MAX_BACKFILL_WEEKS


def _fetch_trades_from_sleeper(
    client: SleeperClient,
    league_id: str,
    *,
    start_week: int,
    min_week: int,
    stop_when: int | None = None,
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for week in range(start_week, min_week - 1, -1):
        try:
            txns = client.get_transactions(league_id, week)
        except Exception:
            continue
        for txn in txns:
            if txn.get("type") != "trade" or txn.get("status") != "complete":
                continue
            txn_id = str(txn.get("transaction_id") or "")
            if not txn_id or txn_id in seen_ids:
                continue
            seen_ids.add(txn_id)
            collected.append(txn)
        if stop_when is not None and len(collected) >= stop_when:
            break

    collected.sort(key=lambda row: int(row.get("created") or 0), reverse=True)
    return collected


def _transaction_context_hash(
    txn: dict[str, Any],
    sides: dict[str, dict[str, Any]],
) -> str:
    payload = {
        "transaction_id": txn.get("transaction_id"),
        "sides": sides,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _upsert_transaction(
    db: Session,
    league_id: str,
    txn: dict[str, Any],
) -> LeagueTransaction:
    txn_id = str(txn["transaction_id"])
    existing = db.scalar(
        select(LeagueTransaction).where(
            LeagueTransaction.league_id == league_id,
            LeagueTransaction.sleeper_transaction_id == txn_id,
        )
    )
    sides = parse_trade_sides(txn)
    if existing is None:
        existing = LeagueTransaction(
            league_id=league_id,
            sleeper_transaction_id=txn_id,
        )
        db.add(existing)

    existing.type = str(txn.get("type") or "trade")
    existing.status = str(txn.get("status") or "complete")
    existing.leg = int(txn["leg"]) if txn.get("leg") is not None else None
    existing.created_ms = int(txn.get("created") or 0)
    existing.roster_ids_json = [str(r) for r in txn.get("roster_ids") or []]
    existing.adds_json = txn.get("adds") or {}
    existing.drops_json = txn.get("drops") or {}
    existing.draft_picks_json = list(txn.get("draft_picks") or [])
    existing.waiver_budget_json = list(txn.get("waiver_budget") or [])
    existing.sides_json = sides
    return existing


def _build_evaluate_request(
    roster_a: str,
    roster_b: str,
    sides: dict[str, dict[str, Any]],
) -> TradeEvaluateRequest:
    side_a = sides[roster_a]
    side_b = sides[roster_b]
    return TradeEvaluateRequest(
        side_a_roster_id=roster_a,
        side_b_roster_id=roster_b,
        side_a_gives=TradeSideInput(
            players=list(side_a["gives"]["players"]),
            picks=[TradePickRef(**p) for p in side_a["gives"]["picks"]],
        ),
        side_b_gives=TradeSideInput(
            players=list(side_b["gives"]["players"]),
            picks=[TradePickRef(**p) for p in side_b["gives"]["picks"]],
        ),
    )


def _analyze_transaction(
    db: Session,
    league_id: str,
    row: LeagueTransaction,
) -> None:
    roster_ids = list(row.roster_ids_json or [])
    sides = dict(row.sides_json or {})

    if len(roster_ids) != 2:
        row.analysis_json = {
            "multi_party": True,
            "skipped": True,
            "error": "AI analysis supports two-team trades only",
        }
        row.analyzed_at = datetime.now(timezone.utc)
        row.analysis_context_hash = _transaction_context_hash(
            {"transaction_id": row.sleeper_transaction_id},
            sides,
        )
        return

    context_hash = _transaction_context_hash(
        {"transaction_id": row.sleeper_transaction_id},
        sides,
    )
    if row.analysis_json and row.analysis_context_hash == context_hash:
        return

    req = _build_evaluate_request(roster_ids[0], roster_ids[1], sides)
    try:
        result = validate_trade_dual(db, league_id, req, include_fix=False)
    except Exception as exc:
        row.analysis_json = {
            "skipped": True,
            "error": f"AI analysis failed: {exc}",
        }
        row.analysis_context_hash = context_hash
        row.analyzed_at = datetime.now(timezone.utc)
        return

    if result is None:
        row.analysis_json = {
            "skipped": True,
            "error": "Could not resolve trade teams",
        }
    else:
        row.tv_evaluation_json = result.evaluation.model_dump()
        row.analysis_json = {
            "side_a": result.side_a.model_dump(),
            "side_b": result.side_b.model_dump(),
            "overall_grade": result.overall_grade,
            "summary": result.summary,
            "tv_fairness_grade": result.evaluation.tv_fairness_grade,
            "favors_roster_id": result.evaluation.favors_roster_id,
            "multi_party": False,
            "skipped": False,
        }

    row.analysis_context_hash = context_hash
    row.analyzed_at = datetime.now(timezone.utc)


def sync_league_trades(
    db: Session,
    league_id: str,
    *,
    client: SleeperClient | None = None,
) -> dict[str, int]:
    """Pull recent trades from Sleeper and upsert — no AI analysis."""
    client = client or SleeperClient()
    stored_count = db.scalar(
        select(func.count())
        .select_from(LeagueTransaction)
        .where(LeagueTransaction.league_id == league_id)
    ) or 0

    current_week = _current_nfl_week(client)
    if stored_count == 0:
        trades = _fetch_trades_from_sleeper(
            client,
            league_id,
            start_week=current_week,
            min_week=max(1, current_week - MAX_BACKFILL_WEEKS + 1),
            stop_when=INITIAL_TRADE_BACKFILL,
        )
        trades = trades[:INITIAL_TRADE_BACKFILL]
    else:
        trades = _fetch_trades_from_sleeper(
            client,
            league_id,
            start_week=current_week,
            min_week=max(1, current_week - INCREMENTAL_WEEK_LOOKBACK + 1),
        )

    new_count = 0
    for txn in trades:
        txn_id = str(txn.get("transaction_id") or "")
        existed = db.scalar(
            select(LeagueTransaction.id).where(
                LeagueTransaction.league_id == league_id,
                LeagueTransaction.sleeper_transaction_id == txn_id,
            )
        )
        _upsert_transaction(db, league_id, txn)
        if existed is None:
            new_count += 1

    db.commit()

    return {
        "trades_fetched": len(trades),
        "trades_new": new_count,
        "trades_stored": db.scalar(
            select(func.count())
            .select_from(LeagueTransaction)
            .where(LeagueTransaction.league_id == league_id)
        )
        or 0,
    }


def analyze_pending_league_trades(
    db: Session,
    league_id: str,
) -> dict[str, int]:
    """Run AI analysis on trades that have not been analyzed yet."""
    if not get_settings().anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured — cannot analyze trades")

    analyzed = 0
    failed = 0
    pending = db.scalars(
        select(LeagueTransaction)
        .where(
            LeagueTransaction.league_id == league_id,
            LeagueTransaction.analysis_json.is_(None),
        )
        .order_by(LeagueTransaction.created_ms.desc())
    ).all()

    for row in pending:
        try:
            _analyze_transaction(db, league_id, row)
            analyzed += 1
        except Exception as exc:
            failed += 1
            row.analysis_json = {
                "skipped": True,
                "error": f"Trade analysis failed: {exc}",
            }
            row.analyzed_at = datetime.now(timezone.utc)

    db.commit()

    remaining = db.scalar(
        select(func.count())
        .select_from(LeagueTransaction)
        .where(
            LeagueTransaction.league_id == league_id,
            LeagueTransaction.analysis_json.is_(None),
        )
    ) or 0

    return {
        "trades_analyzed": analyzed,
        "trades_failed": failed,
        "trades_pending": remaining,
    }


def sync_and_analyze_league_trades(
    db: Session,
    league_id: str,
    *,
    client: SleeperClient | None = None,
) -> dict[str, int]:
    """Backward-compatible helper: sync then analyze."""
    counts = sync_league_trades(db, league_id, client=client)
    try:
        analysis = analyze_pending_league_trades(db, league_id)
    except RuntimeError:
        analysis = {"trades_analyzed": 0, "trades_failed": 0, "trades_pending": 0}
    counts.update(analysis)
    return counts


def _roster_names(db: Session, league_id: str) -> dict[str, str]:
    rows = db.scalars(select(Roster).where(Roster.league_id == league_id)).all()
    return {r.sleeper_roster_id: r.team_name or f"Team {r.sleeper_roster_id}" for r in rows}


def _player_names(db: Session, league_id: str) -> dict[str, str]:
    rows = db.scalars(
        select(PlayerSnapshot).where(PlayerSnapshot.league_id == league_id)
    ).all()
    return {
        r.sleeper_player_id: r.player_name or r.sleeper_player_id
        for r in rows
        if r.sleeper_player_id
    }


def _enrich_asset_players(
    player_ids: list[str],
    names: dict[str, str],
    snapshots: dict[str, PlayerSnapshot],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for pid in player_ids:
        snap = snapshots.get(pid)
        enriched.append(
            {
                "player_id": pid,
                "name": names.get(pid) or pid,
                "position": snap.position if snap else None,
                "tv": snap.trade_value if snap else None,
                "ovr": snap.dynasty_rating if snap else None,
            }
        )
    return enriched


def _pick_labels(db: Session, league_id: str) -> dict[tuple[str, int, str], str]:
    rows = db.scalars(
        select(RosterDraftPick).where(RosterDraftPick.league_id == league_id)
    ).all()
    return {
        (row.season, int(row.round), row.original_roster_id): row.label or ""
        for row in rows
    }


def _enrich_asset_picks(
    picks: list[dict[str, Any]],
    pick_labels: dict[tuple[str, int, str], str],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for p in picks:
        season = str(p.get("season") or "")
        round_no = int(p.get("round") or 0)
        original = str(p.get("original_roster_id") or "")
        label = pick_labels.get((season, round_no, original)) or None
        enriched.append(
            {
                "season": season,
                "round": round_no,
                "original_roster_id": original,
                "label": label,
            }
        )
    return enriched


def get_recent_trades(
    db: Session,
    league_id: str,
    *,
    limit: int = 10,
) -> RecentTradesResponse | None:
    from backend.db.models import League

    if db.get(League, league_id) is None:
        return None

    total = db.scalar(
        select(func.count())
        .select_from(LeagueTransaction)
        .where(LeagueTransaction.league_id == league_id)
    ) or 0

    unanalyzed = db.scalar(
        select(func.count())
        .select_from(LeagueTransaction)
        .where(
            LeagueTransaction.league_id == league_id,
            LeagueTransaction.analysis_json.is_(None),
        )
    ) or 0

    rows = db.scalars(
        select(LeagueTransaction)
        .where(LeagueTransaction.league_id == league_id)
        .order_by(LeagueTransaction.created_ms.desc())
        .limit(limit)
    ).all()

    roster_names = _roster_names(db, league_id)
    player_names = _player_names(db, league_id)
    pick_labels = _pick_labels(db, league_id)
    snapshots = {
        r.sleeper_player_id: r
        for r in db.scalars(
            select(PlayerSnapshot).where(PlayerSnapshot.league_id == league_id)
        ).all()
    }

    trades: list[RecentTrade] = []
    for row in rows:
        sides_out: list[TradeActivitySide] = []
        for roster_id in row.roster_ids_json or []:
            side_data = (row.sides_json or {}).get(str(roster_id)) or _empty_side()
            sides_out.append(
                TradeActivitySide(
                    roster_id=str(roster_id),
                    team_name=roster_names.get(str(roster_id)),
                    gives={
                        "players": _enrich_asset_players(
                            list(side_data.get("gives", {}).get("players") or []),
                            player_names,
                            snapshots,
                        ),
                        "picks": _enrich_asset_picks(
                            list(side_data.get("gives", {}).get("picks") or []),
                            pick_labels,
                        ),
                    },
                    receives={
                        "players": _enrich_asset_players(
                            list(side_data.get("receives", {}).get("players") or []),
                            player_names,
                            snapshots,
                        ),
                        "picks": _enrich_asset_picks(
                            list(side_data.get("receives", {}).get("picks") or []),
                            pick_labels,
                        ),
                    },
                )
            )

        analysis = None
        if row.analysis_json:
            raw = dict(row.analysis_json)
            analysis = TradeActivityAnalysis(
                side_a=TradeSideValidation(**raw["side_a"]) if raw.get("side_a") else None,
                side_b=TradeSideValidation(**raw["side_b"]) if raw.get("side_b") else None,
                overall_grade=raw.get("overall_grade"),
                summary=raw.get("summary"),
                tv_fairness_grade=raw.get("tv_fairness_grade"),
                favors_roster_id=raw.get("favors_roster_id"),
                skipped=bool(raw.get("skipped")),
                error=raw.get("error"),
                multi_party=bool(raw.get("multi_party")),
            )

        trades.append(
            RecentTrade(
                transaction_id=row.sleeper_transaction_id,
                created_ms=row.created_ms,
                leg=row.leg,
                roster_ids=[str(r) for r in row.roster_ids_json or []],
                sides=sides_out,
                waiver_budget=list(row.waiver_budget_json or []),
                analysis=analysis,
            )
        )

    return RecentTradesResponse(trades=trades, total_stored=total, unanalyzed_count=unanalyzed)
