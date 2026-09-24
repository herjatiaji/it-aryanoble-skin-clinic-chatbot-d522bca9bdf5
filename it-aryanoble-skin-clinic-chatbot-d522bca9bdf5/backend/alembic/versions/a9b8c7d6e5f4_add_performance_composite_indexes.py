"""add comprehensive performance composite indexes for all tables and foreign keys

Revision ID: a9b8c7d6e5f4
Revises: f8b9c0d1e2f3
Create Date: 2026-09-23 17:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, None] = 'f8b9c0d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------
    # 1. Chat Subsystem Indexes (Idempotent)
    # -------------------------------------------------------------
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_chat_messages_session_created ON chat_messages (session_id, created_at);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_chat_session_user_status ON chat_session (user_id, status);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_chat_session_branch_id ON chat_session (branch_id);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_chat_session_feedback_issue ON chat_session (has_data_issue, session_type);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_chat_session_updated_at ON chat_session (updated_at);"))

    # -------------------------------------------------------------
    # 2. User & Branch Subsystem Indexes (Idempotent)
    # -------------------------------------------------------------
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_branch_branch_status ON user_branch (branch_id, status);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_branch_user_status ON user_branch (user_id, status);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_branches_code ON branches (code);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_branches_ecosystem ON branches (ecosystem);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_users_type_deleted ON users (type, deleted_at);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_users_dr_type ON users (dr_type);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_users_ecosystem ON users (ecosystem);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_token_usage_user_ym ON user_token_usage (user_id, year_month);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_token_usage_branch_ym ON user_token_usage (branch_id, year_month);"))

    # -------------------------------------------------------------
    # 3. RBAC & Exclusion Junction Table Foreign Key Indexes (Idempotent)
    # -------------------------------------------------------------
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_role_access_access_id ON role_access (access_id);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_access_access_id ON user_access (access_id);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_role_role_id ON user_role (role_id);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_category_exclusion_cat_id ON user_category_exclusion (category_id);"))

    # -------------------------------------------------------------
    # 4. Knowledge & Project Subsystem Indexes (Idempotent)
    # -------------------------------------------------------------
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_knowledge_status_deleted ON knowledge (status, deleted_at);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_knowledge_uploaded_by ON knowledge (uploaded_by);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_knowledge_approved_by ON knowledge (approved_by);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_knowledge_category_cat_id ON knowledge_category (category_id);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_pending_operations_user_status ON pending_operations (user_id, status);"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_projects_created_by ON projects (created_by);"))


def downgrade() -> None:
    # 4. Knowledge & Project (Idempotent)
    op.execute(sa.text("DROP INDEX IF EXISTS ix_projects_created_by;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_pending_operations_user_status;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_category_cat_id;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_approved_by;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_uploaded_by;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_status_deleted;"))

    # 3. RBAC & Exclusion Junctions (Idempotent)
    op.execute(sa.text("DROP INDEX IF EXISTS ix_user_category_exclusion_cat_id;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_user_role_role_id;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_user_access_access_id;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_role_access_access_id;"))

    # 2. User & Branch (Idempotent)
    op.execute(sa.text("DROP INDEX IF EXISTS ix_user_token_usage_branch_ym;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_user_token_usage_user_ym;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_users_ecosystem;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_users_dr_type;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_users_type_deleted;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_branches_ecosystem;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_branches_code;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_user_branch_user_status;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_user_branch_branch_status;"))

    # 1. Chat (Idempotent)
    op.execute(sa.text("DROP INDEX IF EXISTS ix_chat_session_updated_at;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_chat_session_feedback_issue;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_chat_session_branch_id;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_chat_session_user_status;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_chat_messages_session_created;"))


