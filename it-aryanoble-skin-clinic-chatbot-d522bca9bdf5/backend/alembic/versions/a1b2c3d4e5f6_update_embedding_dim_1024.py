"""Update embedding column dimension to 1024

Revision ID: a1b2c3d4e5f6
Revises: f55b221777db
Create Date: 2026-07-22 00:08:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '270b0f97d577'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunk_embedding;")
    op.execute("ALTER TABLE knowledge_chunk ALTER COLUMN embedding TYPE vector(1024);")
    op.create_index(
        'ix_knowledge_chunk_embedding',
        'knowledge_chunk',
        ['embedding'],
        unique=False,
        postgresql_using='hnsw',
        postgresql_with={'m': 16, 'ef_construction': 64},
        postgresql_ops={'embedding': 'vector_cosine_ops'}
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunk_embedding;")
    op.execute("ALTER TABLE knowledge_chunk ALTER COLUMN embedding TYPE vector(1536);")
    op.create_index(
        'ix_knowledge_chunk_embedding',
        'knowledge_chunk',
        ['embedding'],
        unique=False,
        postgresql_using='hnsw',
        postgresql_with={'m': 16, 'ef_construction': 64},
        postgresql_ops={'embedding': 'vector_cosine_ops'}
    )
