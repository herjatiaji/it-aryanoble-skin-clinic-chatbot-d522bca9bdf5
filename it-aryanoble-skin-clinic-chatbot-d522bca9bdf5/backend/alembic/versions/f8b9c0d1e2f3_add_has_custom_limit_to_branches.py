"""add has_custom_limit to branches

Revision ID: f8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-09-23 07:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8b9c0d1e2f3'
down_revision: Union[str, None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'branches',
        sa.Column('has_custom_limit', sa.Boolean(), nullable=False, server_default=sa.text('false'))
    )


def downgrade() -> None:
    op.drop_column('branches', 'has_custom_limit')
