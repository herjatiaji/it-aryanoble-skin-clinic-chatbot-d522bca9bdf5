"""add pending_operations table

Revision ID: e8f9a0b1c2d3
Revises: f7a8b9c0d1e2
Create Date: 2026-09-07 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pending_operations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('knowledge_id', sa.String(length=100), nullable=False),
        sa.Column('target_item', sa.String(length=255), nullable=True),
        sa.Column('context_label', sa.String(length=500), nullable=True),
        sa.Column('field', sa.String(length=100), nullable=True),
        sa.Column('new_value', sa.String(), nullable=True),
        sa.Column('batch_id', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_pending_operations_knowledge_id', 'pending_operations', ['knowledge_id'])
    op.create_index('ix_pending_operations_status', 'pending_operations', ['status'])


def downgrade() -> None:
    op.drop_index('ix_pending_operations_status', table_name='pending_operations')
    op.drop_index('ix_pending_operations_knowledge_id', table_name='pending_operations')
    op.drop_table('pending_operations')
