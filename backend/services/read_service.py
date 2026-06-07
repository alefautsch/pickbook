"""Snapshot read helpers — no scoring at request time (§11)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.db.models import League, LeagueSnapshot, PlayerSnapshot, Roster, SyncRun
from backend.services.history_service import team_ovr_delta
from backend.schemas.analysis import LeagueAnalysis
from backend.schemas.league import LeagueDetail, LeagueRankings, LeagueTeamSummary, LeagueTile
from backend.schemas.player import (
    DynastyComponents,
    PeakWindow,
    PlayerBio,
    PlayerCard,
    PlayerLenses,
    PlayerOutlook,
    PlayerRanks,
    StatisticalPercentiles,
)
from backend.schemas.team import DepthChartGroup, DepthChartPlayer, InjuryWatchItem, LineupSlot, TeamDetail, TeamTrait

SLEEPER_HEADSHOT = "https://sleepercdn.com/content/nfl/players/thumb/{player_id}.jpg"


def ovr_tier(ovr: int | None) -> str | None:
    if ovr is None:
        return None
    if ovr >= 90:
        return "elite"
    if ovr >= 80:
        return "blue-chip"
    if ovr >= 70:
        return "solid"
    if ovr >= 60:
        return "depth"
    return "replacement"


def headshot_url(player_id: str) -> str:
    return SLEEPER_HEADSHOT.format(player_id=player_id)


def _last_synced(db: Session, league_id: str) -> datetime | None:
    return db.scalar(
        select(SyncRun.finished_at)
        .where(SyncRun.league_id == league_id, SyncRun.status == "success")
        .order_by(desc(SyncRun.finished_at))
        .limit(1)
    )


def _latest_league_snapshot(db: Session, league_id: str) -> LeagueSnapshot | None:
    return db.scalar(
        select(LeagueSnapshot)
        .where(LeagueSnapshot.league_id == league_id)
        .order_by(desc(LeagueSnapshot.computed_at))
        .limit(1)
    )


def _outlook_from_snapshot(snapshot: PlayerSnapshot) -> PlayerOutlook:
    raw = snapshot.outlook_json or {}
    peak_raw = raw.get("peak_window") or {}
    pct_raw = raw.get("percentiles") or {}
    return PlayerOutlook(
        archetype=raw.get("archetype"),
        peak_window=PeakWindow(
            years_to_peak=peak_raw.get("years_to_peak"),
            peak_window_end=peak_raw.get("peak_window_end"),
        ),
        opportunity_score=raw.get("opportunity_score") or snapshot.opportunity_score,
        percentiles=StatisticalPercentiles(
            hppg_pct=pct_raw.get("hppg_pct"),
            worp_ppg_pct=pct_raw.get("worp_ppg_pct"),
            tv_pct=pct_raw.get("tv_pct"),
        ),
    )


def _player_card_from_snapshot(snapshot: PlayerSnapshot, league_name: str) -> PlayerCard:
    components_raw = snapshot.components_json or {}
    return PlayerCard(
        player_id=snapshot.sleeper_player_id,
        player_name=snapshot.player_name,
        position=snapshot.position,
        nfl_team=snapshot.nfl_team,
        age=snapshot.age,
        ovr=snapshot.dynasty_rating,
        tier=ovr_tier(snapshot.dynasty_rating),
        dynasty_rookie=snapshot.dynasty_rookie,
        components=DynastyComponents(
            tv=components_raw.get("tv"),
            worp=components_raw.get("worp"),
            per_game=components_raw.get("per_game"),
            upside=components_raw.get("upside"),
            age=components_raw.get("age"),
            trajectory=components_raw.get("trajectory"),
        ),
        lenses=PlayerLenses(
            flex_rating=snapshot.flex_rating,
            win_now_rating=snapshot.win_now_rating,
        ),
        bio=PlayerBio(
            height=snapshot.height,
            weight=snapshot.weight,
            college=snapshot.college,
            years_exp=snapshot.years_exp,
        ),
        ranks=PlayerRanks(
            position_rank=snapshot.position_rank,
            overall_rank=snapshot.overall_rank,
        ),
        hppg=snapshot.hppg,
        worp_ppg=snapshot.worp_ppg,
        availability=snapshot.availability,
        healthy_games=snapshot.healthy_games,
        total_games=snapshot.total_games,
        hppg_expected=snapshot.hppg_expected,
        trade_value=snapshot.trade_value,
        season_worp=snapshot.season_worp,
        porp=snapshot.porp,
        injury_status=snapshot.injury_status,
        injury_body_part=snapshot.injury_body_part,
        projected_ppg=snapshot.projected_ppg,
        projection_source=snapshot.projection_source,
        outlook=_outlook_from_snapshot(snapshot),
        headshot_url=headshot_url(snapshot.sleeper_player_id),
        league_id=snapshot.league_id,
        league_name=league_name,
        computed_at=snapshot.computed_at,
    )


def get_player_card(db: Session, player_id: str, league_id: str) -> PlayerCard | None:
    league = db.get(League, league_id)
    if league is None:
        return None
    snapshot = db.scalar(
        select(PlayerSnapshot).where(
            PlayerSnapshot.league_id == league_id,
            PlayerSnapshot.sleeper_player_id == player_id,
        )
    )
    if snapshot is None:
        return None
    return _player_card_from_snapshot(snapshot, league.name)


def _rank_lookup(rankings: list[dict[str, Any]], roster_id: str, field: str) -> int | None:
    for row in rankings:
        if str(row.get("roster_id")) == roster_id:
            return row.get(field)
    return None


def _merge_team_summaries(snapshot: LeagueSnapshot) -> list[LeagueTeamSummary]:
    rankings = snapshot.rankings_json or {}
    by_dynasty = {str(r["roster_id"]): r for r in rankings.get("by_dynasty", [])}
    by_ppg = {str(r["roster_id"]): r for r in rankings.get("by_starter_ppg", [])}
    by_tv = {str(r["roster_id"]): r for r in rankings.get("by_tv", [])}
    by_win = {str(r["roster_id"]): r for r in rankings.get("by_win_now", [])}

    roster_ids = set(by_dynasty) | set(by_ppg) | set(by_tv) | set(by_win)
    teams: list[LeagueTeamSummary] = []
    for roster_id in sorted(roster_ids):
        base = by_dynasty.get(roster_id) or by_ppg.get(roster_id) or {}
        teams.append(
            LeagueTeamSummary(
                roster_id=roster_id,
                team_name=base.get("team_name"),
                owner=base.get("owner"),
                is_me=bool(base.get("is_me")),
                avg_dynasty_rating=base.get("avg_dynasty_rating"),
                starter_total_ppg=base.get("starter_total_ppg"),
                total_trade_value=base.get("total_trade_value"),
                dynasty_rank=by_dynasty.get(roster_id, {}).get("dynasty_rank"),
                starter_ppg_rank=by_ppg.get(roster_id, {}).get("starter_ppg_rank"),
                tv_rank=by_tv.get(roster_id, {}).get("tv_rank"),
                win_rank=by_win.get(roster_id, {}).get("win_rank"),
                contender_tier=base.get("contender_tier"),
                contender_rank=base.get("contender_rank"),
                contender_score=base.get("contender_score"),
            )
        )
    teams.sort(key=lambda t: t.dynasty_rank or 999)
    return teams


def list_league_tiles(db: Session) -> list[LeagueTile]:
    leagues = db.scalars(select(League).order_by(League.name)).all()
    tiles: list[LeagueTile] = []

    for league in leagues:
        snap = _latest_league_snapshot(db, league.sleeper_league_id)
        my_rank = None
        my_ovr = None
        my_ppg = None
        my_tv = None
        my_ppg_rank = None
        my_tv_rank = None
        my_team_name = None
        my_contender_tier = None
        my_contender_score = None

        if snap is not None:
            for row in snap.rankings_json.get("by_dynasty", []):
                if row.get("is_me"):
                    my_rank = row.get("dynasty_rank")
                    my_ovr = row.get("avg_dynasty_rating")
                    my_ppg = row.get("starter_total_ppg")
                    my_tv = row.get("total_trade_value")
                    my_team_name = row.get("team_name")
                    my_contender_tier = row.get("contender_tier")
                    my_contender_score = row.get("contender_score")
                    break
            for row in snap.rankings_json.get("by_starter_ppg", []):
                if row.get("is_me"):
                    my_ppg_rank = row.get("starter_ppg_rank")
                    break
            for row in snap.rankings_json.get("by_tv", []):
                if row.get("is_me"):
                    my_tv_rank = row.get("tv_rank")
                    break

        my_roster = db.scalar(
            select(Roster).where(Roster.league_id == league.sleeper_league_id, Roster.is_me.is_(True))
        )
        if my_roster and not my_team_name:
            my_team_name = my_roster.team_name

        ovr_delta = None
        if my_roster is not None and my_ovr is not None:
            ovr_delta = team_ovr_delta(
                db,
                league.sleeper_league_id,
                my_roster.sleeper_roster_id,
                my_ovr,
            )

        tiles.append(
            LeagueTile(
                league_id=league.sleeper_league_id,
                name=league.name,
                season=league.season,
                total_rosters=league.total_rosters,
                superflex=league.superflex,
                my_roster_id=my_roster.sleeper_roster_id if my_roster else None,
                my_team_name=my_team_name,
                my_dynasty_rank=my_rank,
                my_roster_ovr=my_ovr,
                my_starter_ppg=my_ppg,
                my_total_trade_value=my_tv,
                my_starter_ppg_rank=my_ppg_rank,
                my_tv_rank=my_tv_rank,
                my_contender_tier=my_contender_tier,
                my_contender_score=my_contender_score,
                my_roster_ovr_delta=ovr_delta,
                last_synced=_last_synced(db, league.sleeper_league_id),
            )
        )
    return tiles


def get_league_analysis(db: Session, league_id: str) -> LeagueAnalysis | None:
    league = db.get(League, league_id)
    if league is None:
        return None
    snap = _latest_league_snapshot(db, league_id)
    if snap is None:
        return LeagueAnalysis(league_id=league_id, league_name=league.name)
    analysis = snap.analysis_json or {}
    return LeagueAnalysis(
        league_id=league_id,
        league_name=league.name,
        computed_at=snap.computed_at,
        contender_index=analysis.get("contender_index"),
        position_strength=analysis.get("position_strength"),
        age_profiles=analysis.get("age_profiles", []),
        trade_surplus=analysis.get("trade_surplus"),
    )


def get_league_detail(db: Session, league_id: str) -> LeagueDetail | None:
    league = db.get(League, league_id)
    if league is None:
        return None
    snap = _latest_league_snapshot(db, league_id)
    teams = _merge_team_summaries(snap) if snap else []
    return LeagueDetail(
        league_id=league.sleeper_league_id,
        name=league.name,
        season=league.season,
        total_rosters=league.total_rosters,
        superflex=league.superflex,
        last_synced=_last_synced(db, league_id),
        teams=teams,
    )


def get_league_rankings(db: Session, league_id: str) -> LeagueRankings | None:
    league = db.get(League, league_id)
    if league is None:
        return None
    snap = _latest_league_snapshot(db, league_id)
    if snap is None:
        return LeagueRankings(league_id=league_id, league_name=league.name)
    rankings = snap.rankings_json or {}
    return LeagueRankings(
        league_id=league_id,
        league_name=league.name,
        computed_at=snap.computed_at,
        by_dynasty=rankings.get("by_dynasty", []),
        by_starter_ppg=rankings.get("by_starter_ppg", []),
        by_tv=rankings.get("by_tv", []),
        by_win_now=rankings.get("by_win_now", []),
    )


def _depth_chart_from_roster(players: list[PlayerCard]) -> list[DepthChartGroup]:
    by_pos: dict[str, list[PlayerCard]] = {}
    for player in players:
        pos = player.position or "UNK"
        by_pos.setdefault(pos, []).append(player)

    groups: list[DepthChartGroup] = []
    for pos in ("QB", "RB", "WR", "TE"):
        if pos not in by_pos:
            continue
        sorted_players = sorted(by_pos[pos], key=lambda p: p.ovr or 0, reverse=True)[:3]
        groups.append(
            DepthChartGroup(
                position=pos,
                players=[
                    DepthChartPlayer(
                        player_id=p.player_id,
                        player_name=p.player_name,
                        ovr=p.ovr,
                        depth_rank=idx,
                    )
                    for idx, p in enumerate(sorted_players, start=1)
                ],
            )
        )
    return groups


def _injuries_from_roster(players: list[PlayerCard]) -> list[InjuryWatchItem]:
    items: list[InjuryWatchItem] = []
    for player in players:
        if not player.injury_status:
            continue
        status = player.injury_status.lower()
        if status in ("healthy", "active", "none", ""):
            continue
        items.append(
            InjuryWatchItem(
                player_id=player.player_id,
                player_name=player.player_name,
                position=player.position,
                injury_status=player.injury_status,
                injury_body_part=player.injury_body_part,
            )
        )
    items.sort(key=lambda row: row.player_name or "")
    return items


def get_team_detail(db: Session, league_id: str, roster_id: str) -> TeamDetail | None:
    league = db.get(League, league_id)
    if league is None:
        return None

    roster = db.scalar(
        select(Roster).where(
            Roster.league_id == league_id,
            Roster.sleeper_roster_id == roster_id,
        )
    )
    if roster is None:
        return None

    snap = _latest_league_snapshot(db, league_id)
    if snap is None:
        return None

    teams_data = (snap.analysis_json or {}).get("teams", {})
    team_lineup = teams_data.get(str(roster_id))
    if team_lineup is None:
        return None

    team_meta = team_lineup

    snapshots = {
        row.sleeper_player_id: row
        for row in db.scalars(
            select(PlayerSnapshot).where(PlayerSnapshot.league_id == league_id)
        ).all()
    }

    def _card(player_id: str | None) -> PlayerCard | None:
        if not player_id:
            return None
        snap_row = snapshots.get(str(player_id))
        if snap_row is None:
            return None
        return _player_card_from_snapshot(snap_row, league.name)

    starters = [
        LineupSlot(slot=row["slot"], player=_card(row.get("player_id")))
        for row in team_lineup.get("starters", [])
    ]
    bench = [_card(pid) for pid in team_lineup.get("bench", [])]
    bench = [card for card in bench if card is not None]

    starter_players = [slot.player for slot in starters if slot.player]
    roster_players = starter_players + bench

    rankings = snap.rankings_json or {}
    dynasty_row = next(
        (r for r in rankings.get("by_dynasty", []) if str(r.get("roster_id")) == roster_id),
        {},
    )
    ppg_row = next(
        (r for r in rankings.get("by_starter_ppg", []) if str(r.get("roster_id")) == roster_id),
        {},
    )
    tv_row = next(
        (r for r in rankings.get("by_tv", []) if str(r.get("roster_id")) == roster_id),
        {},
    )
    win_row = next(
        (r for r in rankings.get("by_win_now", []) if str(r.get("roster_id")) == roster_id),
        {},
    )

    breakdown_raw = team_meta.get("component_breakdown") or {}
    traits_raw = team_meta.get("traits") or []

    return TeamDetail(
        league_id=league_id,
        league_name=league.name,
        roster_id=roster_id,
        team_name=roster.team_name or dynasty_row.get("team_name"),
        owner=roster.owner_name or dynasty_row.get("owner"),
        is_me=roster.is_me,
        avg_dynasty_rating=dynasty_row.get("avg_dynasty_rating"),
        starter_avg_dynasty_rating=dynasty_row.get("starter_avg_dynasty_rating"),
        starter_total_ppg=dynasty_row.get("starter_total_ppg"),
        total_trade_value=dynasty_row.get("total_trade_value"),
        dynasty_rank=dynasty_row.get("dynasty_rank"),
        starter_ppg_rank=ppg_row.get("starter_ppg_rank"),
        tv_rank=tv_row.get("tv_rank"),
        win_rank=win_row.get("win_rank"),
        contender_tier=dynasty_row.get("contender_tier"),
        contender_score=dynasty_row.get("contender_score"),
        component_breakdown=DynastyComponents(
            tv=breakdown_raw.get("tv"),
            worp=breakdown_raw.get("worp"),
            per_game=breakdown_raw.get("per_game"),
            upside=breakdown_raw.get("upside"),
            age=breakdown_raw.get("age"),
            trajectory=breakdown_raw.get("trajectory"),
        ),
        traits=[TeamTrait(label=t["label"], value=t["value"]) for t in traits_raw if t.get("label")],
        starters=starters,
        bench=bench,
        roster=roster_players,
        depth_chart=_depth_chart_from_roster(roster_players),
        injuries=_injuries_from_roster(roster_players),
    )
