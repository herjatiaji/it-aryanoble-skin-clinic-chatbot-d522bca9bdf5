"""add kb_chunk domain, is_discontinued and target_indications

These columns were added to the KBChunk model without a migration, so a database built from migrations alone
(every fresh deployment) lacks them: each chunk insert and each retrieval query then fails, and no document can
be published or found. Idempotent, because databases created another way already have them.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-10-28 15:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE kb_chunk ADD COLUMN IF NOT EXISTS domain VARCHAR(50);"))
    op.execute(sa.text("ALTER TABLE kb_chunk ADD COLUMN IF NOT EXISTS is_discontinued BOOLEAN NOT NULL DEFAULT false;"))
    op.execute(sa.text("ALTER TABLE kb_chunk ADD COLUMN IF NOT EXISTS target_indications TEXT[] NOT NULL DEFAULT '{}'::text[];"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_chunk_domain ON kb_chunk (domain);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_chunk_discontinued ON kb_chunk (is_discontinued);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_chunk_target_indications ON kb_chunk USING GIN (target_indications);"))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_kb_chunk_target_indications;"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_kb_chunk_discontinued;"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_kb_chunk_domain;"))
    op.execute(sa.text("ALTER TABLE kb_chunk DROP COLUMN IF EXISTS target_indications;"))
    op.execute(sa.text("ALTER TABLE kb_chunk DROP COLUMN IF EXISTS is_discontinued;"))
    op.execute(sa.text("ALTER TABLE kb_chunk DROP COLUMN IF EXISTS domain;"))
