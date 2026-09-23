"""change cis_id and external_id to integer, add user_type_code

Revision ID: c1d2e3f4a5b6
Revises: dea79c0745e2
Create Date: 2026-08-14 07:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'dea79c0745e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Alter users.cis_id to Integer
    op.execute("ALTER TABLE users ALTER COLUMN cis_id TYPE INTEGER USING cis_id::integer")
    
    # 2. Alter branches.external_id to Integer
    op.execute("ALTER TABLE branches ALTER COLUMN external_id TYPE INTEGER USING external_id::integer")
    
    # 3. Add user_type_code to users
    op.add_column('users', sa.Column('user_type_code', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'user_type_code')
    op.execute("ALTER TABLE branches ALTER COLUMN external_id TYPE VARCHAR USING external_id::varchar")
    op.execute("ALTER TABLE users ALTER COLUMN cis_id TYPE VARCHAR USING cis_id::varchar")
