"""index only title, section and content of kb_chunk in full-text search

retrieval_text starts with metadata fields ('Type: TREATMENT | Domain: ANTI_AGING | Target Indications:
dull_skin, ... | Title: ... | Section: ... | Content: ...'). Indexed whole, those fields put words such as
'type' (100% of chunks) and 'skin' (78%) into every chunk, so they never discriminate and a query like
'all skin type' cannot match the one section named that way. The metadata fields have their own columns;
the lexical index now covers the title, section and content values only.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-10-25 22:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONTENT_ONLY_TSV = (
    "to_tsvector('simple', regexp_replace(regexp_replace(retrieval_text, "
    "'(^|\\| )(Type|Domain|Status|Target Indications): [^|]*', '', 'g'), "
    "'(Title|Section|Content): ', '', 'g'))"
)


def _recreate_tsv(expression: str) -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_kb_chunk_tsv;"))
    op.execute(sa.text("ALTER TABLE kb_chunk DROP COLUMN IF EXISTS tsv;"))
    op.execute(sa.text(f"ALTER TABLE kb_chunk ADD COLUMN tsv tsvector GENERATED ALWAYS AS ({expression}) STORED;"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_kb_chunk_tsv ON kb_chunk USING GIN (tsv);"))


def upgrade() -> None:
    _recreate_tsv(CONTENT_ONLY_TSV)


def downgrade() -> None:
    _recreate_tsv("to_tsvector('simple', retrieval_text)")
