"""add status and deleted_at to user_branch

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-08-14 16:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add status column (default 1)
    op.add_column('user_branch', sa.Column('status', sa.Integer(), server_default='1', nullable=False))
    
    # 2. Add deleted_at column for soft delete
    op.add_column('user_branch', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('user_branch', 'deleted_at')
    op.drop_column('user_branch', 'status')
