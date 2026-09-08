"""remove has_ai_access

Revision ID: a3b4c5d6e7f8
Revises: a2b3c4d5e6f7
Create Date: 2026-07-31 10:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('users', 'has_ai_access')


def downgrade() -> None:
    op.add_column('users', sa.Column('has_ai_access', sa.Boolean(), server_default='false', nullable=False))
