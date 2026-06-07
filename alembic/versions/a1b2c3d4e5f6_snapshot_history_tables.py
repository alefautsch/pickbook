"""snapshot history tables (Phase 4.5)

Revision ID: a1b2c3d4e5f6
Revises: 286eb21295ab
Create Date: 2026-06-07 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "286eb21295ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "league_snapshot_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("league_id", sa.String(length=32), nullable=False),
        sa.Column("sync_run_id", sa.Integer(), nullable=True),
        sa.Column("context_hash", sa.String(length=64), nullable=True),
        sa.Column("formula_version", sa.String(length=64), nullable=False),
        sa.Column("anchors_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("team_ovr_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.sleeper_league_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sync_run_id"], ["sync_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_league_snapshot_history_league_computed",
        "league_snapshot_history",
        ["league_id", "computed_at"],
    )

    op.create_table(
        "player_snapshot_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("league_id", sa.String(length=32), nullable=False),
        sa.Column("sleeper_player_id", sa.String(length=32), nullable=False),
        sa.Column("league_snapshot_history_id", sa.Integer(), nullable=True),
        sa.Column("player_name", sa.String(length=255), nullable=True),
        sa.Column("position", sa.String(length=8), nullable=True),
        sa.Column("nfl_team", sa.String(length=8), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("dynasty_rating", sa.Integer(), nullable=True),
        sa.Column("dynasty_score", sa.Float(), nullable=True),
        sa.Column("dynasty_rookie", sa.Boolean(), nullable=False),
        sa.Column("components_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("hppg", sa.Float(), nullable=True),
        sa.Column("worp_ppg", sa.Float(), nullable=True),
        sa.Column("availability", sa.Float(), nullable=True),
        sa.Column("hppg_expected", sa.Boolean(), nullable=False),
        sa.Column("trade_value", sa.Float(), nullable=True),
        sa.Column("flex_rating", sa.Integer(), nullable=True),
        sa.Column("season_worp", sa.Float(), nullable=True),
        sa.Column("dynasty_rating_recomputed", sa.Integer(), nullable=True),
        sa.Column("recomputed_formula_version", sa.String(length=64), nullable=True),
        sa.Column("context_hash", sa.String(length=64), nullable=True),
        sa.Column("formula_version", sa.String(length=64), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.sleeper_league_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["league_snapshot_history_id"], ["league_snapshot_history.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_player_snapshot_history_player_league_computed",
        "player_snapshot_history",
        ["league_id", "sleeper_player_id", "computed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_player_snapshot_history_player_league_computed", table_name="player_snapshot_history")
    op.drop_table("player_snapshot_history")
    op.drop_index("ix_league_snapshot_history_league_computed", table_name="league_snapshot_history")
    op.drop_table("league_snapshot_history")
