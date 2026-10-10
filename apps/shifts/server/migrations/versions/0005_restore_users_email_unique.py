"""Restore the email uniqueness inadvertently omitted by 0004's batch schema.

Revision ID: 0005_users_email_unique
Revises: 0004_ttlock_access
"""

from alembic import op

revision = "0005_users_email_unique"
down_revision = "0004_ttlock_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A unique index preserves the auth contract without rewriting SQLite tables.
    op.create_index("uq_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_users_email", table_name="users")
