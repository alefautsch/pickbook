"""opportunity and projection fields (Phase 5)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-07 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_projection_columns(table: str) -> None:
    op.add_column(table, sa.Column("opportunity_score", sa.Float(), nullable=True))
    op.add_column(table, sa.Column("projected_ppg", sa.Float(), nullable=True))
    op.add_column(table, sa.Column("projection_source", sa.String(length=32), nullable=True))
    op.add_column(
        table,
        sa.Column(
            "outlook_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def upgrade() -> None:
    _add_projection_columns("player_snapshots")
    _add_projection_columns("player_snapshot_history")
    op.add_column("player_snapshot_history", sa.Column("win_now_rating", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("player_snapshot_history", "win_now_rating")
    for table in ("player_snapshots", "player_snapshot_history"):
        op.drop_column(table, "outlook_json")
        op.drop_column(table, "projection_source")
        op.drop_column(table, "projected_ppg")
        op.drop_column(table, "opportunity_score")
