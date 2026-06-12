"""add memory links

Revision ID: 20260611_0002
Revises: 20260610_0001
Create Date: 2026-06-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260611_0002"
down_revision = "20260610_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("from_memory_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_memory_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_type", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.85", nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["from_memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "from_memory_id",
            "to_memory_id",
            "link_type",
            name="uq_memory_links_from_to_type",
        ),
    )
    op.create_index("ix_memory_links_from_memory_id", "memory_links", ["from_memory_id"])
    op.create_index("ix_memory_links_to_memory_id", "memory_links", ["to_memory_id"])
    op.create_index("ix_memory_links_link_type", "memory_links", ["link_type"])


def downgrade() -> None:
    op.drop_index("ix_memory_links_link_type", table_name="memory_links")
    op.drop_index("ix_memory_links_to_memory_id", table_name="memory_links")
    op.drop_index("ix_memory_links_from_memory_id", table_name="memory_links")
    op.drop_table("memory_links")
