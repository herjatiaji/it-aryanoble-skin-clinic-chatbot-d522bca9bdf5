"""add feedback fields to chat_session

Revision ID: dea79c0745e2
Revises: ef5f540160e5
Create Date: 2026-08-11 08:49:07.603325

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dea79c0745e2'
down_revision: Union[str, None] = 'ef5f540160e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chat_session', sa.Column('has_data_issue', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('chat_session', sa.Column('is_feedback_read', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('chat_session', 'is_feedback_read')
    op.drop_column('chat_session', 'has_data_issue')
