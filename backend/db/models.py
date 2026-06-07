from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class League(Base):
    """Sleeper league identity + scoring/roster settings (§10)."""

    __tablename__ = "leagues"

    sleeper_league_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    season: Mapped[str] = mapped_column(String(8), nullable=False, default="2026")
    total_rosters: Mapped[int] = mapped_column(Integer, nullable=False)
    superflex: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scoring_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    roster_positions_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    rosters: Mapped[list[Roster]] = relationship(back_populates="league", cascade="all, delete-orphan")
    player_snapshots: Mapped[list[PlayerSnapshot]] = relationship(
        back_populates="league", cascade="all, delete-orphan"
    )
    league_snapshots: Mapped[list[LeagueSnapshot]] = relationship(
        back_populates="league", cascade="all, delete-orphan"
    )
    sync_runs: Mapped[list[SyncRun]] = relationship(back_populates="league")
    player_snapshot_history: Mapped[list[PlayerSnapshotHistory]] = relationship(
        back_populates="league", cascade="all, delete-orphan"
    )
    league_snapshot_history: Mapped[list[LeagueSnapshotHistory]] = relationship(
        back_populates="league", cascade="all, delete-orphan"
    )


class Roster(Base):
    """One team's roster in a league."""

    __tablename__ = "rosters"
    __table_args__ = (UniqueConstraint("league_id", "sleeper_roster_id", name="uq_roster_league_sleeper"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("leagues.sleeper_league_id", ondelete="CASCADE"), nullable=False
    )
    sleeper_roster_id: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(String(32))
    owner_name: Mapped[str | None] = mapped_column(String(255))
    team_name: Mapped[str | None] = mapped_column(String(255))
    is_me: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    league: Mapped[League] = relationship(back_populates="rosters")
    players: Mapped[list[RosterPlayer]] = relationship(
        back_populates="roster", cascade="all, delete-orphan"
    )


class RosterPlayer(Base):
    """Player ownership on a roster."""

    __tablename__ = "roster_players"
    __table_args__ = (UniqueConstraint("roster_id", "sleeper_player_id", name="uq_roster_player"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    roster_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rosters.id", ondelete="CASCADE"), nullable=False
    )
    sleeper_player_id: Mapped[str] = mapped_column(String(32), nullable=False)
    player_name: Mapped[str | None] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(8))
    nfl_team: Mapped[str | None] = mapped_column(String(8))

    roster: Mapped[Roster] = relationship(back_populates="players")


class PlayerSnapshot(Base):
    """Per (league, player) computed grade — what the UI reads (§5.7, §10)."""

    __tablename__ = "player_snapshots"
    __table_args__ = (UniqueConstraint("league_id", "sleeper_player_id", name="uq_player_snapshot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("leagues.sleeper_league_id", ondelete="CASCADE"), nullable=False
    )
    sleeper_player_id: Mapped[str] = mapped_column(String(32), nullable=False)
    player_name: Mapped[str | None] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(8))
    nfl_team: Mapped[str | None] = mapped_column(String(8))
    age: Mapped[int | None] = mapped_column(Integer)

    dynasty_rating: Mapped[int | None] = mapped_column(Integer)
    dynasty_score: Mapped[float | None] = mapped_column(Float)
    dynasty_rookie: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    components_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    hppg: Mapped[float | None] = mapped_column(Float)
    worp_ppg: Mapped[float | None] = mapped_column(Float)
    availability: Mapped[float | None] = mapped_column(Float)
    hppg_expected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trade_value: Mapped[float | None] = mapped_column(Float)
    flex_rating: Mapped[int | None] = mapped_column(Integer)
    win_now_rating: Mapped[int | None] = mapped_column(Integer)

    context_hash: Mapped[str | None] = mapped_column(String(64))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    league: Mapped[League] = relationship(back_populates="player_snapshots")


class LeagueSnapshot(Base):
    """Per-league precomputed rankings and analysis (§10)."""

    __tablename__ = "league_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("leagues.sleeper_league_id", ondelete="CASCADE"), nullable=False
    )
    rankings_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    analysis_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    context_hash: Mapped[str | None] = mapped_column(String(64))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    league: Mapped[League] = relationship(back_populates="league_snapshots")


class SyncRun(Base):
    """Observability for sync jobs (§10)."""

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("leagues.sleeper_league_id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    counts_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    errors_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    league: Mapped[League | None] = relationship(back_populates="sync_runs")


class UserSetting(Base):
    """Global knobs migrated from config.json (§10)."""

    __tablename__ = "user_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LeagueSnapshotHistory(Base):
    """League anchor state per sync — enables league-faithful re-curve (§15.1)."""

    __tablename__ = "league_snapshot_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("leagues.sleeper_league_id", ondelete="CASCADE"), nullable=False
    )
    sync_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sync_runs.id", ondelete="SET NULL")
    )
    context_hash: Mapped[str | None] = mapped_column(String(64))
    formula_version: Mapped[str] = mapped_column(String(64), nullable=False)
    anchors_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    team_ovr_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    league: Mapped[League] = relationship(back_populates="league_snapshot_history")
    sync_run: Mapped[SyncRun | None] = relationship()
    player_rows: Mapped[list[PlayerSnapshotHistory]] = relationship(back_populates="league_snapshot")


class PlayerSnapshotHistory(Base):
    """Append-only input ledger per sync (§15.1)."""

    __tablename__ = "player_snapshot_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("leagues.sleeper_league_id", ondelete="CASCADE"), nullable=False
    )
    sleeper_player_id: Mapped[str] = mapped_column(String(32), nullable=False)
    league_snapshot_history_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("league_snapshot_history.id", ondelete="SET NULL")
    )

    player_name: Mapped[str | None] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(8))
    nfl_team: Mapped[str | None] = mapped_column(String(8))
    age: Mapped[int | None] = mapped_column(Integer)

    dynasty_rating: Mapped[int | None] = mapped_column(Integer)
    dynasty_score: Mapped[float | None] = mapped_column(Float)
    dynasty_rookie: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    components_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    hppg: Mapped[float | None] = mapped_column(Float)
    worp_ppg: Mapped[float | None] = mapped_column(Float)
    availability: Mapped[float | None] = mapped_column(Float)
    hppg_expected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trade_value: Mapped[float | None] = mapped_column(Float)
    flex_rating: Mapped[int | None] = mapped_column(Integer)
    season_worp: Mapped[float | None] = mapped_column(Float)

    dynasty_rating_recomputed: Mapped[int | None] = mapped_column(Integer)
    recomputed_formula_version: Mapped[str | None] = mapped_column(String(64))

    context_hash: Mapped[str | None] = mapped_column(String(64))
    formula_version: Mapped[str] = mapped_column(String(64), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    league: Mapped[League] = relationship(back_populates="player_snapshot_history")
    league_snapshot: Mapped[LeagueSnapshotHistory | None] = relationship(back_populates="player_rows")
