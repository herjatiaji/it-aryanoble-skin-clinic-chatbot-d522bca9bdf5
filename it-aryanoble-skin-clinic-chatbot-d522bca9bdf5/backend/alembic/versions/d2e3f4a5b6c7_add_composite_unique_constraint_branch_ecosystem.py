"""add composite unique constraint branch ecosystem and code ecosystem index

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-08-14 16:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop existing single-column unique constraint on branches.external_id
    op.drop_constraint('branches_external_id_key', 'branches', type_='unique')
    
    # 2. Create composite unique constraint on (ecosystem, external_id)
    op.create_unique_constraint(
        'uq_branch_ecosystem_external_id',
        'branches',
        ['ecosystem', 'external_id']
    )
    
    # 3. Create index on (code, ecosystem) for quick branch_code resolution
    op.create_index(
        'ix_branches_code_ecosystem',
        'branches',
        ['code', 'ecosystem'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_branches_code_ecosystem', table_name='branches')
    op.drop_constraint('uq_branch_ecosystem_external_id', 'branches', type_='unique')
    op.create_unique_constraint('branches_external_id_key', 'branches', ['external_id'])
