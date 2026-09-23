"""add session_type and nullable branch_id to chat_session

Revision ID: f7a8b9c0d1e2
Revises: c5d6e7f8a9b0
Create Date: 2026-08-26 10:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Make chat_session.branch_id nullable
    op.alter_column('chat_session', 'branch_id', nullable=True)

    # 2. Add session_type to chat_session
    op.add_column(
        'chat_session',
        sa.Column('session_type', sa.String(length=50), nullable=False, server_default='DOCTOR')
    )


def downgrade() -> None:
    # 1. Remove session_type
    op.drop_column('chat_session', 'session_type')

    # 2. Make branch_id non-nullable again
    op.alter_column('chat_session', 'branch_id', nullable=False)
