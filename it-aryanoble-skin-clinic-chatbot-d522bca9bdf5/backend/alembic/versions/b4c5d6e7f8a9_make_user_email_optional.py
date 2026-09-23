"""make user email optional and update check constraints

Revision ID: b4c5d6e7f8a9
Revises: e4f5a6b7c8d9
Create Date: 2026-08-19 11:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Make users.email nullable
    op.alter_column('users', 'email', nullable=True)

    # 2. Update chk_user_email constraint to allow NULL and support all valid domain TLDs
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_user_email;")
    op.execute("""
        ALTER TABLE users 
        ADD CONSTRAINT chk_user_email 
        CHECK (email IS NULL OR email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$');
    """)

    # 3. Update chk_user_integrity constraint to require email for STAFF but optional for DOCTOR
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_user_integrity;")
    op.execute("""
        ALTER TABLE users 
        ADD CONSTRAINT chk_user_integrity 
        CHECK ((type = 'DOCTOR' AND cis_id IS NOT NULL) OR (type = 'STAFF' AND password_hash IS NOT NULL AND email IS NOT NULL));
    """)


def downgrade() -> None:
    # Revert check constraints
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_user_integrity;")
    op.execute("""
        ALTER TABLE users 
        ADD CONSTRAINT chk_user_integrity 
        CHECK ((type = 'DOCTOR' AND cis_id IS NOT NULL) OR (type = 'STAFF' AND password_hash IS NOT NULL));
    """)

    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_user_email;")
    op.execute("""
        ALTER TABLE users 
        ADD CONSTRAINT chk_user_email 
        CHECK (email ~* '^[A-Za-z0-9._%-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,4}$');
    """)

    # Make users.email NOT NULL (only if no null values exist)
    op.alter_column('users', 'email', nullable=False)
