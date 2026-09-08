"""rename user_category to user_category_exclusion

Revision ID: 2352bcc97f16
Revises: a3b4c5d6e7f8
Create Date: 2026-07-31 11:24:46.933782

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2352bcc97f16'
down_revision: Union[str, None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table('user_category', 'user_category_exclusion')
    op.execute('DELETE FROM user_category_exclusion')


def downgrade() -> None:
    op.rename_table('user_category_exclusion', 'user_category')
