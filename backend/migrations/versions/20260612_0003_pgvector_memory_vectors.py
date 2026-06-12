"""move vector recall into PostgreSQL pgvector

Revision ID: 20260612_0003
Revises: 20260611_0002
Create Date: 2026-06-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260612_0003"
down_revision = "20260611_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "memory_vectors",
        sa.Column("memory_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.Column(
            "payload",
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
        sa.ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("memory_id"),
    )
    op.execute(
        "ALTER TABLE memory_vectors "
        "ALTER COLUMN embedding TYPE vector(384) USING embedding::vector(384)"
    )
    op.create_index(
        "ix_memory_vectors_payload_gin",
        "memory_vectors",
        ["payload"],
        postgresql_using="gin",
    )
    op.execute(
        "CREATE INDEX ix_memory_vectors_embedding_hnsw "
        "ON memory_vectors USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memory_vectors_embedding_hnsw")
    op.drop_index("ix_memory_vectors_payload_gin", table_name="memory_vectors")
    op.drop_table("memory_vectors")
