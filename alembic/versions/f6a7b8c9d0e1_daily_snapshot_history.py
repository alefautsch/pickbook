"""Bound snapshot history by calendar date

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-08 04:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("league_snapshot_history", sa.Column("snapshot_date", sa.Date(), nullable=True))
    op.add_column("player_snapshot_history", sa.Column("snapshot_date", sa.Date(), nullable=True))

    op.execute("UPDATE league_snapshot_history SET snapshot_date = computed_at::date")
    op.execute("UPDATE player_snapshot_history SET snapshot_date = computed_at::date")

    # Keep the newest league snapshot per league/date and point player rows at that kept row.
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                league_id,
                snapshot_date,
                FIRST_VALUE(id) OVER (
                    PARTITION BY league_id, snapshot_date
                    ORDER BY computed_at DESC, id DESC
                ) AS keep_id,
                ROW_NUMBER() OVER (
                    PARTITION BY league_id, snapshot_date
                    ORDER BY computed_at DESC, id DESC
                ) AS rn
            FROM league_snapshot_history
        )
        UPDATE player_snapshot_history p
        SET league_snapshot_history_id = ranked.keep_id
        FROM ranked
        WHERE p.league_snapshot_history_id = ranked.id
          AND ranked.rn > 1
        """
    )
    op.execute(
        """
        DELETE FROM league_snapshot_history l
        USING (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY league_id, snapshot_date
                        ORDER BY computed_at DESC, id DESC
                    ) AS rn
                FROM league_snapshot_history
            ) ranked
            WHERE rn > 1
        ) stale
        WHERE l.id = stale.id
        """
    )

    # Keep the newest player snapshot per player/date.
    op.execute(
        """
        DELETE FROM player_snapshot_history p
        USING (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY league_id, sleeper_player_id, snapshot_date
                        ORDER BY computed_at DESC, id DESC
                    ) AS rn
                FROM player_snapshot_history
            ) ranked
            WHERE rn > 1
        ) stale
        WHERE p.id = stale.id
        """
    )

    op.alter_column("league_snapshot_history", "snapshot_date", nullable=False)
    op.alter_column("player_snapshot_history", "snapshot_date", nullable=False)

    op.create_unique_constraint(
        "uq_league_snapshot_history_date",
        "league_snapshot_history",
        ["league_id", "snapshot_date"],
    )
    op.create_unique_constraint(
        "uq_player_snapshot_history_date",
        "player_snapshot_history",
        ["league_id", "sleeper_player_id", "snapshot_date"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_player_snapshot_history_date",
        "player_snapshot_history",
        type_="unique",
    )
    op.drop_constraint(
        "uq_league_snapshot_history_date",
        "league_snapshot_history",
        type_="unique",
    )
    op.drop_column("player_snapshot_history", "snapshot_date")
    op.drop_column("league_snapshot_history", "snapshot_date")
