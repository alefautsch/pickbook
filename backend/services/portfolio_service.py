"""Cross-league portfolio reads — snapshot + roster joins only (§7, §11)."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import League, PlayerSnapshot, Roster, RosterPlayer
from backend.schemas.free_agent import FreeAgentBoard, FreeAgentRow
from backend.schemas.portfolio import (
    PlayerHoldings,
    PlayerSearchHit,
    PlayerSearchLeagueMatch,
    PlayerSearchResults,
    PortfolioLeagueHolding,
    PortfolioPlayer,
    PortfolioSummary,
    PositionExposure,
)
from backend.services.read_service import headshot_url, ovr_tier


def _rostered_player_ids(db: Session, league_id: str) -> set[str]:
    rows = db.execute(
        select(RosterPlayer.sleeper_player_id)
        .join(Roster, Roster.id == RosterPlayer.roster_id)
        .where(Roster.league_id == league_id)
    ).all()
    return {str(row[0]) for row in rows}


def _my_roster_player_ids(db: Session, league_id: str) -> set[str]:
    rows = db.execute(
        select(RosterPlayer.sleeper_player_id)
        .join(Roster, Roster.id == RosterPlayer.roster_id)
        .where(Roster.league_id == league_id, Roster.is_me.is_(True))
    ).all()
    return {str(row[0]) for row in rows}


def _exposure_flag(league_count: int, total_leagues: int, ages: list[int | None], ovrs: list[int | None]) -> str | None:
    if league_count < 2:
        return None
    avg_ovr = sum(ovr for ovr in ovrs if ovr is not None) / max(len([o for o in ovrs if o is not None]), 1)
    avg_age = sum(age for age in ages if age is not None) / max(len([a for a in ages if a is not None]), 1)
    if league_count >= total_leagues and avg_ovr >= 85 and avg_age <= 27:
        return "conviction"
    if league_count >= 2 and (avg_age >= 30 or avg_ovr < 70):
        return "risk"
    if league_count >= total_leagues:
        return "concentrated"
    return None


def get_portfolio(db: Session) -> PortfolioSummary:
    leagues = db.scalars(select(League).order_by(League.name)).all()
    total_leagues = len(leagues)
    if total_leagues == 0:
        return PortfolioSummary(total_leagues=0, unique_players=0, multi_league_count=0)

    by_player: dict[str, PortfolioPlayer] = {}
    position_counts: dict[str, int] = defaultdict(int)
    position_unique: dict[str, set[str]] = defaultdict(set)

    for league in leagues:
        my_roster = db.scalar(
            select(Roster).where(Roster.league_id == league.sleeper_league_id, Roster.is_me.is_(True))
        )
        if my_roster is None:
            continue

        roster_players = db.scalars(
            select(RosterPlayer).where(RosterPlayer.roster_id == my_roster.id)
        ).all()
        snapshots = {
            row.sleeper_player_id: row
            for row in db.scalars(
                select(PlayerSnapshot).where(PlayerSnapshot.league_id == league.sleeper_league_id)
            ).all()
        }

        for rp in roster_players:
            snap = snapshots.get(rp.sleeper_player_id)
            player_id = rp.sleeper_player_id
            holding = PortfolioLeagueHolding(
                league_id=league.sleeper_league_id,
                league_name=league.name,
                ovr=snap.dynasty_rating if snap else None,
                tier=ovr_tier(snap.dynasty_rating) if snap else None,
                team_name=my_roster.team_name,
            )

            if player_id not in by_player:
                by_player[player_id] = PortfolioPlayer(
                    player_id=player_id,
                    player_name=(snap.player_name if snap else rp.player_name),
                    position=(snap.position if snap else rp.position),
                    nfl_team=(snap.nfl_team if snap else rp.nfl_team),
                    age=snap.age if snap else None,
                    headshot_url=headshot_url(player_id),
                    league_count=0,
                    leagues=[],
                )

            entry = by_player[player_id]
            entry.leagues.append(holding)
            entry.league_count = len(entry.leagues)
            if snap:
                entry.player_name = snap.player_name or entry.player_name
                entry.position = snap.position or entry.position
                entry.nfl_team = snap.nfl_team or entry.nfl_team
                entry.age = snap.age

            pos = (entry.position or "UNK").upper()
            position_counts[pos] += 1
            position_unique[pos].add(player_id)

    holdings = sorted(by_player.values(), key=lambda row: (-row.league_count, row.player_name or ""))
    multi_league = [row for row in holdings if row.league_count >= 2]

    for row in holdings:
        ages = [row.age] * row.league_count if row.age is not None else []
        ovrs = [league.ovr for league in row.leagues if league.ovr is not None]
        row.exposure_flag = _exposure_flag(row.league_count, total_leagues, ages, ovrs)

    by_position = [
        PositionExposure(
            position=pos,
            holding_count=position_counts[pos],
            unique_players=len(position_unique[pos]),
        )
        for pos in sorted(position_counts)
    ]

    return PortfolioSummary(
        total_leagues=total_leagues,
        unique_players=len(holdings),
        multi_league_count=len(multi_league),
        holdings=holdings,
        by_position=by_position,
    )


def get_player_holdings(db: Session, player_id: str) -> PlayerHoldings | None:
    leagues = db.scalars(select(League).order_by(League.name)).all()
    holdings: list[PortfolioLeagueHolding] = []
    player_name: str | None = None
    position: str | None = None

    for league in leagues:
        my_ids = _my_roster_player_ids(db, league.sleeper_league_id)
        if player_id not in my_ids:
            continue

        my_roster = db.scalar(
            select(Roster).where(Roster.league_id == league.sleeper_league_id, Roster.is_me.is_(True))
        )
        snap = db.scalar(
            select(PlayerSnapshot).where(
                PlayerSnapshot.league_id == league.sleeper_league_id,
                PlayerSnapshot.sleeper_player_id == player_id,
            )
        )
        if snap:
            player_name = snap.player_name or player_name
            position = snap.position or position

        holdings.append(
            PortfolioLeagueHolding(
                league_id=league.sleeper_league_id,
                league_name=league.name,
                ovr=snap.dynasty_rating if snap else None,
                tier=ovr_tier(snap.dynasty_rating) if snap else None,
                team_name=my_roster.team_name if my_roster else None,
            )
        )

    if not holdings:
        return None

    return PlayerHoldings(
        player_id=player_id,
        player_name=player_name,
        position=position,
        leagues=holdings,
    )


def search_players(db: Session, query: str, *, limit: int = 25) -> PlayerSearchResults:
    q = query.strip()
    if len(q) < 2:
        return PlayerSearchResults(query=q, hits=[])

    pattern = f"%{q}%"
    snapshots = db.scalars(
        select(PlayerSnapshot)
        .where(PlayerSnapshot.player_name.ilike(pattern))
        .order_by(PlayerSnapshot.dynasty_rating.desc().nullslast())
    ).all()

    leagues = {row.sleeper_league_id: row for row in db.scalars(select(League)).all()}
    owned_by_league: dict[str, set[str]] = {}
    for league_id in leagues:
        owned_by_league[league_id] = _my_roster_player_ids(db, league_id)

    by_player: dict[str, list[PlayerSnapshot]] = defaultdict(list)
    for snap in snapshots:
        by_player[snap.sleeper_player_id].append(snap)

    hits: list[PlayerSearchHit] = []
    for player_id, snaps in by_player.items():
        if len(hits) >= limit:
            break
        snaps_sorted = sorted(
            snaps,
            key=lambda row: (row.dynasty_rating or 0),
            reverse=True,
        )
        first = snaps_sorted[0]
        league_matches = []
        for snap in snaps_sorted:
            league = leagues.get(snap.league_id)
            if league is None:
                continue
            league_matches.append(
                PlayerSearchLeagueMatch(
                    league_id=snap.league_id,
                    league_name=league.name,
                    ovr=snap.dynasty_rating,
                    tier=ovr_tier(snap.dynasty_rating),
                    is_owned=player_id in owned_by_league.get(snap.league_id, set()),
                )
            )

        hits.append(
            PlayerSearchHit(
                player_id=player_id,
                player_name=first.player_name,
                position=first.position,
                nfl_team=first.nfl_team,
                headshot_url=headshot_url(player_id),
                leagues=league_matches,
            )
        )

    return PlayerSearchResults(query=q, hits=hits)


def _position_matches_filter(position: str | None, filter_pos: str | None, superflex: bool) -> bool:
    if not filter_pos:
        return True
    pos = (position or "").upper()
    filt = filter_pos.upper().replace("-", "_")
    if filt in {"SF", "SUPER_FLEX", "SUPERFLEX"}:
        return pos == "QB" if superflex else False
    if filt == "FLEX":
        return pos in {"RB", "WR", "TE"}
    return pos == filt


def get_free_agents(
    db: Session,
    league_id: str,
    *,
    position: str | None = None,
) -> FreeAgentBoard | None:
    league = db.get(League, league_id)
    if league is None:
        return None

    rostered = _rostered_player_ids(db, league_id)
    fa_pool_size = get_settings().fa_pool_size

    snapshots = db.scalars(
        select(PlayerSnapshot)
        .where(PlayerSnapshot.league_id == league_id)
        .order_by(PlayerSnapshot.dynasty_rating.desc().nullslast())
    ).all()

    fa_rows: list[FreeAgentRow] = []
    for snap in snapshots:
        if snap.sleeper_player_id in rostered:
            continue
        if not _position_matches_filter(snap.position, position, league.superflex):
            continue
        fa_rows.append(
            FreeAgentRow(
                player_id=snap.sleeper_player_id,
                player_name=snap.player_name,
                position=snap.position,
                nfl_team=snap.nfl_team,
                age=snap.age,
                ovr=snap.dynasty_rating,
                tier=ovr_tier(snap.dynasty_rating),
                dynasty_rookie=snap.dynasty_rookie,
                hppg=snap.hppg,
                projected_ppg=snap.projected_ppg,
                worp_ppg=snap.worp_ppg,
                trade_value=snap.trade_value,
                hppg_expected=snap.hppg_expected,
                headshot_url=headshot_url(snap.sleeper_player_id),
                league_id=league_id,
                league_name=league.name,
                computed_at=snap.computed_at,
            )
        )

    return FreeAgentBoard(
        league_id=league_id,
        league_name=league.name,
        superflex=league.superflex,
        position_filter=position,
        fa_pool_size=fa_pool_size,
        total_available=len(fa_rows),
        players=fa_rows,
    )
