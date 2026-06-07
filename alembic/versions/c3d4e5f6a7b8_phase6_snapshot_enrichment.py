"""Phase 6 snapshot enrichment — ranks, WORP/PORP, bio, injury, actv games

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-07 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_player_columns(table: str, *, skip_season_worp: bool = False) -> None:
    if not skip_season_worp:
        op.add_column(table, sa.Column("season_worp", sa.Float(), nullable=True))
    op.add_column(table, sa.Column("porp", sa.Float(), nullable=True))
    op.add_column(table, sa.Column("healthy_games", sa.Integer(), nullable=True))
    op.add_column(table, sa.Column("total_games", sa.Integer(), nullable=True))
    op.add_column(table, sa.Column("injury_status", sa.String(length=32), nullable=True))
    op.add_column(table, sa.Column("injury_body_part", sa.String(length=64), nullable=True))
    op.add_column(table, sa.Column("height", sa.String(length=16), nullable=True))
    op.add_column(table, sa.Column("weight", sa.String(length=16), nullable=True))
    op.add_column(table, sa.Column("college", sa.String(length=128), nullable=True))
    op.add_column(table, sa.Column("years_exp", sa.Integer(), nullable=True))
    op.add_column(table, sa.Column("position_rank", sa.Integer(), nullable=True))
    op.add_column(table, sa.Column("overall_rank", sa.Integer(), nullable=True))


def upgrade() -> None:
    _add_player_columns("player_snapshots")
    _add_player_columns("player_snapshot_history", skip_season_worp=True)


def downgrade() -> None:
    cols = (
        "overall_rank",
        "position_rank",
        "years_exp",
        "college",
        "weight",
        "height",
        "injury_body_part",
        "injury_status",
        "total_games",
        "healthy_games",
        "porp",
        "season_worp",
    )
    for table in ("player_snapshots", "player_snapshot_history"):
        for col in cols:
            op.drop_column(table, col)
