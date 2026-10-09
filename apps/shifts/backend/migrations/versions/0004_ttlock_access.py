"""Add the TTLock access permission and issuance ledger.

Revision ID: 0004_ttlock_access
Revises: 0003_drop_team_phone
Create Date: 2026-10-08

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_ttlock_access"
down_revision: Union[str, Sequence[str], None] = "0003_drop_team_phone"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _users(as_left: bool = True) -> sa.Table:
    columns = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=300), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notify_email", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    ]
    constraints: list = [sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("username")]
    if not as_left:
        columns.insert(7, sa.Column("can_request_pin", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        constraints.append(sa.UniqueConstraint("email", name="uq_users_email"))
    return sa.Table("users", sa.MetaData(), *columns, *constraints)


def upgrade() -> None:
    with op.batch_alter_table("users", copy_from=_users()) as batch_op:
        batch_op.add_column(
            sa.Column("can_request_pin", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )

    op.create_table(
        "access_pins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("assignment_id", sa.Integer(), nullable=True),
        sa.Column("lock_id", sa.String(length=128), nullable=True),
        sa.Column("keyboard_pwd_id", sa.String(length=128), nullable=True),
        sa.Column("encrypted_pin", sa.String(length=512), nullable=True),
        sa.Column("valid_from_utc", sa.DateTime(), nullable=False),
        sa.Column("valid_until_utc", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("request_key", sa.String(length=200), nullable=False),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at_utc", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_key", name="uq_access_pins_request_key"),
    )


def downgrade() -> None:
    op.drop_table("access_pins")

    with op.batch_alter_table("users", copy_from=_users(as_left=False)) as batch_op:
        batch_op.drop_column("can_request_pin")
