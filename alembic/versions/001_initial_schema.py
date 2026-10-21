"""initial schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-10-21 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. links table
    op.create_table(
        "links",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_links_code"), "links", ["code"], unique=True)

    # 2. clicks table
    op.create_table(
        "clicks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("link_id", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["link_id"], ["links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index(
        "ix_clicks_link_id_clicked_at",
        "clicks",
        ["link_id", "clicked_at"],
        unique=False,
    )

    # 3. daily_click_counts table
    op.create_table(
        "daily_click_counts",
        sa.Column("link_id", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("count", sa.BigInteger(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["link_id"], ["links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("link_id", "day"),
    )


def downgrade() -> None:
    op.drop_table("daily_click_counts")
    op.drop_index("ix_clicks_link_id_clicked_at", table_name="clicks")
    op.drop_table("clicks")
    op.drop_index(op.f("ix_links_code"), table_name="links")
    op.drop_table("links")
