"""Drop the team phone number.

E-mail already moved onto the user in 0002, and phone was the last contact left
on the team itself: nothing reads it anywhere. Removing it keeps the team a pure
rota concept.

Revision ID: 0003_drop_team_phone
Revises: 0002_notifications_by_user
Create Date: 2026-10-08

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_drop_team_phone"
down_revision: Union[str, Sequence[str], None] = "0002_notifications_by_user"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _teams(with_phone: bool) -> sa.Table:
    """The teams table, spelled out so the batch rewrite never depends on reflection."""
    columns = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("calendar_token", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    ]
    constraints = [
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("calendar_token"),
    ]
    if with_phone:
        columns.insert(3, sa.Column("phone", sa.String(length=40), nullable=True))
    return sa.Table("teams", sa.MetaData(), *columns, *constraints)


def upgrade() -> None:
    with op.batch_alter_table("teams", copy_from=_teams(with_phone=True)) as batch_op:
        batch_op.drop_column("phone")


def downgrade() -> None:
    with op.batch_alter_table("teams", copy_from=_teams(with_phone=False)) as batch_op:
        batch_op.add_column(sa.Column("phone", sa.String(length=40), nullable=True))