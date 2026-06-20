"""league_transactions for synced trade history + AI analysis

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-06-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, Sequence[str], None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "league_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("league_id", sa.String(length=32), nullable=False),
        sa.Column("sleeper_transaction_id", sa.String(length=32), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("leg", sa.Integer(), nullable=True),
        sa.Column("created_ms", sa.Integer(), nullable=False),
        sa.Column("roster_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("adds_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("drops_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("draft_picks_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("waiver_budget_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sides_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tv_evaluation_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("analysis_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("analysis_context_hash", sa.String(length=64), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.sleeper_league_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "league_id", "sleeper_transaction_id", name="uq_league_transaction"
        ),
    )
    op.create_index(
        "ix_league_transactions_league_created",
        "league_transactions",
        ["league_id", "created_ms"],
    )


def downgrade() -> None:
    op.drop_index("ix_league_transactions_league_created", table_name="league_transactions")
    op.drop_table("league_transactions")
