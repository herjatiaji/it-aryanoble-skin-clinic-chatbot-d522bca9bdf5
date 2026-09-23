"""update token usage and add ingestion usage

Revision ID: e4f5a6b7c8d9
Revises: e3f4a5b6c7d8
Create Date: 2026-08-19 08:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update user_token_usage table:
    op.execute("""
    DO $$ 
    BEGIN
        -- Add id column if not exists
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name='user_token_usage' AND column_name='id'
        ) THEN
            ALTER TABLE user_token_usage DROP CONSTRAINT IF EXISTS user_token_usage_pkey;
            ALTER TABLE user_token_usage ADD COLUMN id UUID PRIMARY KEY DEFAULT gen_random_uuid();
        END IF;

        -- Add branch_id column if not exists
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name='user_token_usage' AND column_name='branch_id'
        ) THEN
            ALTER TABLE user_token_usage ADD COLUMN branch_id UUID REFERENCES branches(id) ON DELETE CASCADE;
        END IF;

        -- Add input_tokens column if not exists
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name='user_token_usage' AND column_name='input_tokens'
        ) THEN
            ALTER TABLE user_token_usage ADD COLUMN input_tokens INTEGER NOT NULL DEFAULT 0;
        END IF;

        -- Add output_tokens column if not exists
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name='user_token_usage' AND column_name='output_tokens'
        ) THEN
            ALTER TABLE user_token_usage ADD COLUMN output_tokens INTEGER NOT NULL DEFAULT 0;
        END IF;

        -- Add unique constraint on (user_id, branch_id, year_month) if not exists
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'uq_user_branch_year_month'
        ) THEN
            ALTER TABLE user_token_usage ADD CONSTRAINT uq_user_branch_year_month UNIQUE (user_id, branch_id, year_month);
        END IF;
    END $$;
    """)

    # 2. Create ingestion_token_usage table if not exists (single statement per execute)
    op.execute("""
    CREATE TABLE IF NOT EXISTS ingestion_token_usage (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        year_month VARCHAR(7) UNIQUE NOT NULL,
        input_tokens INTEGER NOT NULL DEFAULT 0,
        output_tokens INTEGER NOT NULL DEFAULT 0,
        tokens_used INTEGER NOT NULL DEFAULT 0,
        documents_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_ingestion_tokens_used_positive CHECK (tokens_used >= 0)
    )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS ix_ingestion_token_usage_year_month ON ingestion_token_usage(year_month)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ingestion_token_usage CASCADE")
    op.execute("""
    DO $$
    BEGIN
        ALTER TABLE user_token_usage DROP CONSTRAINT IF EXISTS uq_user_branch_year_month;
        ALTER TABLE user_token_usage DROP COLUMN IF EXISTS output_tokens;
        ALTER TABLE user_token_usage DROP COLUMN IF EXISTS input_tokens;
        ALTER TABLE user_token_usage DROP COLUMN IF EXISTS branch_id;
    END $$;
    """)
