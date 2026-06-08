"""roster_draft_picks table for in-season pick inventory

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-07 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "roster_draft_picks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("league_id", sa.String(length=32), nullable=False),
        sa.Column("owner_roster_id", sa.String(length=32), nullable=False),
        sa.Column("original_roster_id", sa.String(length=32), nullable=False),
        sa.Column("season", sa.String(length=8), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("slot_tier", sa.String(length=16), nullable=False),
        sa.Column("trade_value", sa.Float(), nullable=True),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["league_id"],
            ["leagues.sleeper_league_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "league_id",
            "season",
            "round",
            "original_roster_id",
            name="uq_roster_draft_pick_slot",
        ),
    )
    op.create_index(
        "ix_roster_draft_picks_league_owner",
        "roster_draft_picks",
        ["league_id", "owner_roster_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_roster_draft_picks_league_owner", table_name="roster_draft_picks")
    op.drop_table("roster_draft_picks")
