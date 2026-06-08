"""Advisor tool implementations — on-demand league data for the in-season tool loop."""

from __future__ import annotations

import ast
import json
import operator
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import League, PlayerSnapshot, Roster, RosterDraftPick
from backend.services.web_search_service import search_web
from backend.services.analysis_service import TRADE_SURPLUS_BOTTOM_N, TRADE_SURPLUS_TOP_N
from backend.services.pick_service import get_roster_draft_picks
from backend.services.portfolio_service import get_free_agents
from backend.services.read_service import get_league_rankings, get_player_card, get_team_detail

FAIRNESS_BAND = 0.05
TOP_FA_DEFAULT = 24
TOP_ROSTER_PLAYERS = 16

_CALC_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_calculate(expression: str) -> float:
    """Evaluate a numeric expression with + - * / ** and parentheses only."""
    expr = expression.strip()
    if not expr:
        raise ValueError("expression is required")
    tree = ast.parse(expr, mode="eval")

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError("only numeric literals allowed")
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _CALC_OPS:
                raise ValueError(f"unsupported operator: {op_type.__name__}")
            return _CALC_OPS[op_type](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in _CALC_OPS:
                raise ValueError(f"unsupported operator: {op_type.__name__}")
            return _CALC_OPS[op_type](_eval(node.operand))
        raise ValueError("unsupported expression")

    return round(_eval(tree), 4)


def _pick_key(pick: dict[str, Any]) -> tuple[str, int, str]:
    return (str(pick["season"]), int(pick["round"]), str(pick["original_roster_id"]))


def _fairness_band(give_total: float, receive_total: float) -> dict[str, Any]:
    baseline = max(give_total, receive_total, 1.0)
    net = receive_total - give_total
    pct = net / baseline
    within = abs(pct) <= FAIRNESS_BAND
    if within:
        label = "fair"
    elif pct > 0:
        label = "favors_you"
    else:
        label = "favors_counterparty"
    return {
        "give_total_tv": round(give_total, 2),
        "receive_total_tv": round(receive_total, 2),
        "net_delta_tv": round(net, 2),
        "net_delta_pct": round(pct * 100, 2),
        "fairness_band": f"±{int(FAIRNESS_BAND * 100)}%",
        "fairness": label,
        "within_band": within,
    }


def _positional_notes(
    give_players: list[dict[str, Any]],
    receive_players: list[dict[str, Any]],
) -> list[str]:
    notes: list[str] = []
    give_by_pos: dict[str, int] = {}
    recv_by_pos: dict[str, int] = {}
    for row in give_players:
        pos = row.get("position") or row.get("pos") or "?"
        give_by_pos[pos] = give_by_pos.get(pos, 0) + 1
    for row in receive_players:
        pos = row.get("position") or row.get("pos") or "?"
        recv_by_pos[pos] = recv_by_pos.get(pos, 0) + 1
    for pos, count in recv_by_pos.items():
        if give_by_pos.get(pos, 0) < count:
            notes.append(f"Receive {count} {pos} — fills a roster hole")
    for pos, count in give_by_pos.items():
        if recv_by_pos.get(pos, 0) < count:
            notes.append(f"Give {count} {pos} — moves surplus depth")
    if not notes:
        notes.append("Positional swap is roughly neutral")
    return notes


def evaluate_trade_package(
    give: dict[str, Any],
    receive: dict[str, Any],
    *,
    resolve_player: Callable[[str], dict[str, Any] | None],
    resolve_pick: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> dict[str, Any]:
    """Pure TV evaluation for player + pick packages."""
    give_players_raw = give.get("players") or []
    recv_players_raw = receive.get("players") or []
    give_picks_raw = give.get("picks") or []
    recv_picks_raw = receive.get("picks") or []

    give_players: list[dict[str, Any]] = []
    recv_players: list[dict[str, Any]] = []
    missing: list[str] = []

    for pid in give_players_raw:
        row = resolve_player(str(pid))
        if row is None:
            missing.append(f"player:{pid}")
            continue
        give_players.append(row)
    for pid in recv_players_raw:
        row = resolve_player(str(pid))
        if row is None:
            missing.append(f"player:{pid}")
            continue
        recv_players.append(row)

    give_picks: list[dict[str, Any]] = []
    recv_picks: list[dict[str, Any]] = []
    for pick in give_picks_raw:
        row = resolve_pick(pick)
        if row is None:
            missing.append(f"pick:{_pick_key(pick)}")
            continue
        give_picks.append(row)
    for pick in recv_picks_raw:
        row = resolve_pick(pick)
        if row is None:
            missing.append(f"pick:{_pick_key(pick)}")
            continue
        recv_picks.append(row)

    give_total = sum(p.get("tv") or 0 for p in give_players) + sum(
        p.get("trade_value") or 0 for p in give_picks
    )
    receive_total = sum(p.get("tv") or 0 for p in recv_players) + sum(
        p.get("trade_value") or 0 for p in recv_picks
    )

    fairness = _fairness_band(give_total, receive_total)
    return {
        **fairness,
        "give": {
            "players": give_players,
            "picks": give_picks,
        },
        "receive": {
            "players": recv_players,
            "picks": recv_picks,
        },
        "positional_notes": _positional_notes(give_players, recv_players),
        "missing_assets": missing,
    }


def _team_surplus_needs(
    position_strength: dict[str, Any] | None,
    roster_id: str,
    *,
    top_n: int = TRADE_SURPLUS_TOP_N,
    bottom_n: int = TRADE_SURPLUS_BOTTOM_N,
) -> dict[str, list[dict[str, Any]]]:
    if not position_strength:
        return {"surplus": [], "needs": []}
    teams = position_strength.get("teams") or []
    positions = position_strength.get("positions") or []
    team = next((t for t in teams if str(t.get("roster_id")) == str(roster_id)), None)
    if team is None:
        return {"surplus": [], "needs": []}

    surplus: list[dict[str, Any]] = []
    needs: list[dict[str, Any]] = []
    for pos in positions:
        ranked = sorted(
            [
                {
                    "roster_id": str(t["roster_id"]),
                    "avg_ovr": (t.get("by_position") or {}).get(pos),
                }
                for t in teams
                if (t.get("by_position") or {}).get(pos) is not None
            ],
            key=lambda row: row["avg_ovr"] or 0,
            reverse=True,
        )
        if not ranked:
            continue
        rank_by_roster = {row["roster_id"]: idx + 1 for idx, row in enumerate(ranked)}
        my_rank = rank_by_roster.get(str(roster_id))
        my_ovr = (team.get("by_position") or {}).get(pos)
        if my_rank is None:
            continue
        item = {
            "position": pos,
            "avg_ovr": my_ovr,
            "league_rank": my_rank,
            "league_size": len(ranked),
        }
        if my_rank <= top_n:
            surplus.append(item)
        if my_rank > len(ranked) - bottom_n:
            needs.append(item)
    return {"surplus": surplus, "needs": needs}


def _players_for_roster(
    snapshots: dict[str, PlayerSnapshot],
    roster_player_ids: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pid in roster_player_ids:
        snap = snapshots.get(pid)
        if snap is None:
            continue
        rows.append(
            {
                "player_id": snap.sleeper_player_id,
                "name": snap.player_name,
                "position": snap.position,
                "pos": snap.position,
                "ovr": snap.dynasty_rating,
                "tv": snap.trade_value,
                "hppg": snap.hppg,
            }
        )
    rows.sort(key=lambda r: r.get("tv") or 0, reverse=True)
    return rows


def _balance_with_pick(
    give_assets: list[dict[str, Any]],
    recv_assets: list[dict[str, Any]],
    *,
    my_picks: list[dict[str, Any]],
    their_picks: list[dict[str, Any]],
    target_delta: float = 0.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Add at most one pick to move TV delta toward target."""
    give_tv = sum(a.get("tv") or a.get("trade_value") or 0 for a in give_assets)
    recv_tv = sum(a.get("tv") or a.get("trade_value") or 0 for a in recv_assets)
    delta = recv_tv - give_tv - target_delta
    if abs(delta) <= max(recv_tv, give_tv, 1) * FAIRNESS_BAND:
        return give_assets, recv_assets

    if delta < 0:
        # Need to add to receive side (or remove from give) — add their pick
        for pick in sorted(their_picks, key=lambda p: p.get("trade_value") or 0):
            if abs((recv_tv + (pick.get("trade_value") or 0)) - give_tv) < abs(delta):
                return give_assets, recv_assets + [pick]
    else:
        for pick in sorted(my_picks, key=lambda p: p.get("trade_value") or 0):
            if abs(recv_tv - (give_tv + (pick.get("trade_value") or 0))) < abs(delta):
                return give_assets + [pick], recv_assets
    return give_assets, recv_assets


def generate_trade_suggestions(
    *,
    my_roster_id: str,
    trade_surplus: dict[str, Any] | None,
    roster_players: dict[str, list[dict[str, Any]]],
    picks_by_roster: dict[str, list[dict[str, Any]]],
    target_roster_id: str | None = None,
    max_suggestions: int = 5,
) -> list[dict[str, Any]]:
    """Deterministic trade packages from trade_surplus + rosters + pick TV."""
    if not trade_surplus:
        return []

    my_players = roster_players.get(str(my_roster_id), [])
    my_surplus_positions = {row["position"] for row in trade_surplus.get("surplus") or []}
    my_need_positions = {row["position"] for row in trade_surplus.get("needs") or []}

    counterparties = trade_surplus.get("counterparties") or []
    if target_roster_id:
        counterparties = [
            c for c in counterparties if str(c.get("roster_id")) == str(target_roster_id)
        ]

    seen: set[tuple[str, str, str]] = set()
    suggestions: list[dict[str, Any]] = []

    for cp in counterparties:
        their_id = str(cp.get("roster_id") or "")
        pos = cp.get("position") or ""
        direction = cp.get("direction") or ""
        key = (their_id, pos, direction)
        if key in seen or not their_id:
            continue
        seen.add(key)

        their_players = roster_players.get(their_id, [])
        if not their_players:
            continue

        if direction == "sell" and pos not in my_surplus_positions:
            continue
        if direction == "buy" and pos not in my_need_positions:
            continue

        if direction == "sell":
            give_pool = [p for p in my_players if p.get("position") == pos][-3:]
            recv_pool = [
                p
                for p in their_players
                if p.get("position") in my_need_positions and p.get("position") != pos
            ][:4]
        else:
            recv_pool = [p for p in their_players if p.get("position") == pos][:3]
            give_pool = [
                p
                for p in my_players
                if p.get("position") in my_surplus_positions and p.get("position") != pos
            ][-3:]

        if not give_pool or not recv_pool:
            continue

        give_asset = give_pool[0]
        recv_asset = max(recv_pool, key=lambda p: p.get("tv") or 0)

        give_list: list[dict[str, Any]] = [give_asset]
        recv_list: list[dict[str, Any]] = [recv_asset]

        # Try 2-for-2 if single swap is lopsided
        eval_single = _fairness_band(
            give_asset.get("tv") or 0,
            recv_asset.get("tv") or 0,
        )
        if not eval_single["within_band"] and len(give_pool) > 1 and len(recv_pool) > 1:
            give_list = give_pool[:2]
            recv_list = sorted(recv_pool, key=lambda p: p.get("tv") or 0, reverse=True)[:2]

        give_list, recv_list = _balance_with_pick(
            give_list,
            recv_list,
            my_picks=picks_by_roster.get(str(my_roster_id), []),
            their_picks=picks_by_roster.get(their_id, []),
        )

        give_tv = sum(a.get("tv") or a.get("trade_value") or 0 for a in give_list)
        recv_tv = sum(a.get("tv") or a.get("trade_value") or 0 for a in recv_list)
        fairness = _fairness_band(give_tv, recv_tv)

        suggestions.append(
            {
                "counterparty": {
                    "roster_id": their_id,
                    "team_name": cp.get("team_name"),
                    "direction": direction,
                    "position_hook": pos,
                },
                "give": {
                    "players": [p for p in give_list if p.get("player_id")],
                    "picks": [p for p in give_list if not p.get("player_id")],
                },
                "receive": {
                    "players": [p for p in recv_list if p.get("player_id")],
                    "picks": [p for p in recv_list if not p.get("player_id")],
                },
                **fairness,
                "rationale": (
                    f"{'Sell' if direction == 'sell' else 'Buy'} {pos} leverage — "
                    f"they rank #{cp.get('their_rank')} at {pos}, you rank #{cp.get('my_rank')}"
                ),
            }
        )
        if len(suggestions) >= max_suggestions:
            break

    suggestions.sort(key=lambda s: abs(s.get("net_delta_pct") or 999))
    return suggestions[:max_suggestions]


@dataclass
class AdvisorToolContext:
    db: Session
    league_id: str
    my_roster_id: str
    focused_roster_id: str


class AdvisorTools:
    def __init__(self, ctx: AdvisorToolContext):
        self.ctx = ctx
        self._snapshots: dict[str, PlayerSnapshot] | None = None
        self._pick_index: dict[tuple[str, int, str], dict[str, Any]] | None = None

    def _load_snapshots(self) -> dict[str, PlayerSnapshot]:
        if self._snapshots is None:
            self._snapshots = {
                row.sleeper_player_id: row
                for row in self.ctx.db.scalars(
                    select(PlayerSnapshot).where(
                        PlayerSnapshot.league_id == self.ctx.league_id
                    )
                ).all()
            }
        return self._snapshots

    def _load_pick_index(self) -> dict[tuple[str, int, str], dict[str, Any]]:
        if self._pick_index is None:
            rows = self.ctx.db.scalars(
                select(RosterDraftPick).where(
                    RosterDraftPick.league_id == self.ctx.league_id
                )
            ).all()
            self._pick_index = {
                (row.season, row.round, row.original_roster_id): {
                    "season": row.season,
                    "round": row.round,
                    "original_roster_id": row.original_roster_id,
                    "owner_roster_id": row.owner_roster_id,
                    "slot_tier": row.slot_tier,
                    "trade_value": row.trade_value,
                    "label": row.label,
                }
                for row in rows
            }
        return self._pick_index

    def _resolve_player(self, player_id: str) -> dict[str, Any] | None:
        snap = self._load_snapshots().get(player_id)
        if snap is None:
            return None
        return {
            "player_id": snap.sleeper_player_id,
            "name": snap.player_name,
            "position": snap.position,
            "ovr": snap.dynasty_rating,
            "tv": snap.trade_value,
            "hppg": snap.hppg,
            "injury": snap.injury_status,
        }

    def _resolve_pick(self, pick: dict[str, Any]) -> dict[str, Any] | None:
        key = _pick_key(pick)
        return self._load_pick_index().get(key)

    def _roster_player_ids(self, roster_id: str) -> list[str]:
        roster = self.ctx.db.scalar(
            select(Roster).where(
                Roster.league_id == self.ctx.league_id,
                Roster.sleeper_roster_id == roster_id,
            )
        )
        if roster is None:
            return []
        from backend.db.models import RosterPlayer

        return [
            rp.sleeper_player_id
            for rp in self.ctx.db.scalars(
                select(RosterPlayer).where(RosterPlayer.roster_id == roster.id)
            ).all()
        ]

    def _position_strength(self) -> dict[str, Any] | None:
        from backend.services.read_service import get_league_analysis

        analysis = get_league_analysis(self.ctx.db, self.ctx.league_id)
        if analysis is None or analysis.position_strength is None:
            return None
        return analysis.position_strength.model_dump()

    def _trade_surplus(self) -> dict[str, Any] | None:
        from backend.services.read_service import get_league_analysis

        analysis = get_league_analysis(self.ctx.db, self.ctx.league_id)
        if analysis is None or analysis.trade_surplus is None:
            return None
        return analysis.trade_surplus.model_dump()

    def get_team(self, roster_id: str) -> dict[str, Any]:
        detail = get_team_detail(self.ctx.db, self.ctx.league_id, str(roster_id))
        if detail is None:
            return {"error": f"Team {roster_id} not found"}

        pos_info = _team_surplus_needs(self._position_strength(), str(roster_id))
        players = [
            {
                "player_id": p.player_id,
                "name": p.player_name,
                "pos": p.position,
                "ovr": p.ovr,
                "tv": p.trade_value,
                "hppg": p.hppg,
            }
            for p in detail.roster[:TOP_ROSTER_PLAYERS]
        ]
        return {
            "roster_id": detail.roster_id,
            "team_name": detail.team_name,
            "is_me": detail.is_me,
            "dynasty_rank": detail.dynasty_rank,
            "contender_tier": detail.contender_tier,
            "avg_dynasty_rating": detail.avg_dynasty_rating,
            "starter_total_ppg": detail.starter_total_ppg,
            "total_trade_value": detail.total_trade_value,
            "draft_pick_value": detail.draft_pick_value,
            "needs": pos_info["needs"],
            "surplus": pos_info["surplus"],
            "starter_needs": _starter_needs_from_detail(detail),
            "draft_picks": [p.model_dump() for p in detail.draft_picks],
            "players": players,
            "injuries": [i.model_dump() for i in detail.injuries],
        }

    def get_player(self, player_id: str) -> dict[str, Any]:
        card = get_player_card(self.ctx.db, str(player_id), self.ctx.league_id)
        if card is None:
            return {"error": f"Player {player_id} not found in league pool"}
        return {
            "player_id": card.player_id,
            "name": card.player_name,
            "position": card.position,
            "ovr": card.ovr,
            "tv": card.trade_value,
            "hppg": card.hppg,
            "hppg_expected": card.hppg_expected,
            "worp_ppg": card.worp_ppg,
            "injury_status": card.injury_status,
            "injury_body_part": card.injury_body_part,
            "outlook": card.outlook,
            "win_now_rating": card.lenses.win_now_rating if card.lenses else None,
            "age": card.age,
        }

    def search_players(self, query: str, position: str | None = None) -> dict[str, Any]:
        q = query.strip()
        if len(q) < 2:
            return {"query": q, "hits": [], "note": "query must be at least 2 characters"}

        pattern = f"%{q}%"
        snaps = self.ctx.db.scalars(
            select(PlayerSnapshot)
            .where(
                PlayerSnapshot.league_id == self.ctx.league_id,
                PlayerSnapshot.player_name.ilike(pattern),
            )
            .order_by(PlayerSnapshot.dynasty_rating.desc().nullslast())
            .limit(30)
        ).all()

        rostered: set[str] = set()
        for roster in self.ctx.db.scalars(
            select(Roster).where(Roster.league_id == self.ctx.league_id)
        ).all():
            rostered.update(self._roster_player_ids(roster.sleeper_roster_id))

        hits: list[dict[str, Any]] = []
        for snap in snaps:
            if position and snap.position != position.upper():
                continue
            hits.append(
                {
                    "player_id": snap.sleeper_player_id,
                    "name": snap.player_name,
                    "position": snap.position,
                    "ovr": snap.dynasty_rating,
                    "tv": snap.trade_value,
                    "rostered": snap.sleeper_player_id in rostered,
                }
            )
            if len(hits) >= 20:
                break
        return {"query": q, "position_filter": position, "hits": hits}

    def get_league_rankings(self) -> dict[str, Any]:
        rankings = get_league_rankings(self.ctx.db, self.ctx.league_id)
        if rankings is None:
            return {"error": "Rankings not available — sync the league first"}

        def _row(team: dict[str, Any]) -> dict[str, Any]:
            return {
                "team": team.get("team_name"),
                "roster_id": team.get("roster_id"),
                "is_me": team.get("is_me"),
                "avg_dynasty_rating": team.get("avg_dynasty_rating"),
                "starter_total_ppg": team.get("starter_total_ppg"),
                "total_trade_value": team.get("total_trade_value"),
                "draft_pick_value": team.get("draft_pick_value"),
                "dynasty_rank": team.get("dynasty_rank"),
                "starter_ppg_rank": team.get("starter_ppg_rank"),
                "tv_rank": team.get("tv_rank"),
                "win_rank": team.get("win_rank"),
                "contender_tier": team.get("contender_tier"),
            }

        return {
            "by_dynasty": [_row(t) for t in rankings.by_dynasty],
            "by_starter_ppg": [_row(t) for t in rankings.by_starter_ppg],
            "by_trade_value": [_row(t) for t in rankings.by_tv],
            "by_win_now": [_row(t) for t in rankings.by_win_now],
        }

    def get_free_agents(
        self,
        position: str | None = None,
        limit: int = TOP_FA_DEFAULT,
    ) -> dict[str, Any]:
        board = get_free_agents(self.ctx.db, self.ctx.league_id, position=position)
        if board is None:
            return {"players": []}
        cap = max(1, min(int(limit), 50))
        return {
            "position_filter": position,
            "total_available": board.total_available,
            "players": [
                {
                    "player_id": row.player_id,
                    "name": row.player_name,
                    "position": row.position,
                    "ovr": row.ovr,
                    "tv": row.trade_value,
                    "hppg": row.hppg,
                    "hppg_expected": row.hppg_expected,
                }
                for row in board.players[:cap]
            ],
        }

    def evaluate_trade(self, give: dict[str, Any], receive: dict[str, Any]) -> dict[str, Any]:
        return evaluate_trade_package(
            give,
            receive,
            resolve_player=self._resolve_player,
            resolve_pick=self._resolve_pick,
        )

    def suggest_trades(self, target_roster_id: str | None = None) -> dict[str, Any]:
        trade_surplus = self._trade_surplus()
        snapshots = self._load_snapshots()

        roster_players: dict[str, list[dict[str, Any]]] = {}
        picks_by_roster: dict[str, list[dict[str, Any]]] = {}

        for roster in self.ctx.db.scalars(
            select(Roster).where(Roster.league_id == self.ctx.league_id)
        ).all():
            rid = roster.sleeper_roster_id
            roster_players[rid] = _players_for_roster(
                snapshots, self._roster_player_ids(rid)
            )
            picks_by_roster[rid] = get_roster_draft_picks(
                self.ctx.db, self.ctx.league_id, rid
            )

        packages = generate_trade_suggestions(
            my_roster_id=self.ctx.my_roster_id,
            trade_surplus=trade_surplus,
            roster_players=roster_players,
            picks_by_roster=picks_by_roster,
            target_roster_id=target_roster_id,
        )
        return {
            "my_roster_id": self.ctx.my_roster_id,
            "target_roster_id": target_roster_id,
            "trade_surplus_summary": {
                "surplus": (trade_surplus or {}).get("surplus") or [],
                "needs": (trade_surplus or {}).get("needs") or [],
            },
            "packages": packages,
        }

    def calculate(self, expression: str) -> dict[str, Any]:
        try:
            value = safe_calculate(expression)
            return {"expression": expression, "result": value}
        except (ValueError, SyntaxError, ZeroDivisionError) as exc:
            return {"expression": expression, "error": str(exc)}

    def web_search(self, query: str) -> dict[str, Any]:
        settings = get_settings()
        return search_web(query, api_key=settings.brave_api_key)

    def dispatch(self, name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        if name == "get_team":
            return self.get_team(str(tool_input.get("roster_id", "")))
        if name == "get_player":
            return self.get_player(str(tool_input.get("player_id", "")))
        if name == "search_players":
            return self.search_players(
                str(tool_input.get("query", "")),
                tool_input.get("position"),
            )
        if name == "get_league_rankings":
            return self.get_league_rankings()
        if name == "get_free_agents":
            return self.get_free_agents(
                tool_input.get("position"),
                int(tool_input.get("limit") or TOP_FA_DEFAULT),
            )
        if name == "evaluate_trade":
            return self.evaluate_trade(
                tool_input.get("give") or {},
                tool_input.get("receive") or {},
            )
        if name == "suggest_trades":
            tid = tool_input.get("target_roster_id")
            return self.suggest_trades(str(tid) if tid else None)
        if name == "calculate":
            return self.calculate(str(tool_input.get("expression", "")))
        if name == "web_search":
            return self.web_search(str(tool_input.get("query", "")))
        return {"error": f"Unknown tool: {name}"}


def _starter_needs_from_detail(detail: Any) -> dict[str, int]:
    from collections import defaultdict

    counts: dict[str, int] = defaultdict(int)
    for group in detail.depth_chart:
        counts[group.position] = len(group.players)
    needs: dict[str, int] = {}
    targets = {"QB": 2, "RB": 4, "WR": 5, "TE": 2}
    for pos, target in targets.items():
        gap = max(0, target - counts.get(pos, 0))
        if gap:
            needs[pos] = gap
    flex_depth = counts.get("RB", 0) + counts.get("WR", 0) + counts.get("TE", 0)
    needs["FLEX"] = max(0, 3 - flex_depth)
    return needs


ADVISOR_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "get_team",
        "description": "Roster summary: players, positional needs/surplus, valued draft picks, injuries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "roster_id": {"type": "string", "description": "Sleeper roster id"},
            },
            "required": ["roster_id"],
        },
    },
    {
        "name": "get_player",
        "description": "Player card: OVR, TV, HPPG, injury, outlook, win-now lens.",
        "input_schema": {
            "type": "object",
            "properties": {
                "player_id": {"type": "string", "description": "Sleeper player id"},
            },
            "required": ["player_id"],
        },
    },
    {
        "name": "search_players",
        "description": "Search league player pool by name (optional position filter).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "position": {"type": "string", "description": "QB, RB, WR, or TE"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_league_rankings",
        "description": "Dynasty, starter PPG, trade value, and win-now standings.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_free_agents",
        "description": "Top available free agents by OVR/TV.",
        "input_schema": {
            "type": "object",
            "properties": {
                "position": {"type": "string"},
                "limit": {"type": "integer", "description": "Max rows (default 24)"},
            },
        },
    },
    {
        "name": "evaluate_trade",
        "description": (
            "Evaluate a trade package. Players by sleeper_player_id; picks by "
            "{season, round, original_roster_id}. Returns TV totals, net delta, fairness band."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "give": {
                    "type": "object",
                    "properties": {
                        "players": {"type": "array", "items": {"type": "string"}},
                        "picks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "season": {"type": "string"},
                                    "round": {"type": "integer"},
                                    "original_roster_id": {"type": "string"},
                                },
                                "required": ["season", "round", "original_roster_id"],
                            },
                        },
                    },
                },
                "receive": {
                    "type": "object",
                    "properties": {
                        "players": {"type": "array", "items": {"type": "string"}},
                        "picks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "season": {"type": "string"},
                                    "round": {"type": "integer"},
                                    "original_roster_id": {"type": "string"},
                                },
                                "required": ["season", "round", "original_roster_id"],
                            },
                        },
                    },
                },
            },
            "required": ["give", "receive"],
        },
    },
    {
        "name": "suggest_trades",
        "description": (
            "Deterministic trade ideas from trade_surplus, league rosters, and pick TV. "
            "Returns 3–5 balanced packages; narrate with manager names."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_roster_id": {
                    "type": "string",
                    "description": "Optional counterparty roster id",
                },
            },
        },
    },
    {
        "name": "calculate",
        "description": "Safe arithmetic for TV sums (numbers, + - * / **, parentheses).",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string"},
            },
            "required": ["expression"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Search the web for recent NFL injury updates, roster news, and beat reports. "
            "Use for time-sensitive context not in league snapshots (not for player TV/OVR)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    },
]


def tool_result_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str)
