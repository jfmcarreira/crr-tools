"""Notifications are addressed to the user, never to the team.

The address and the opt-in flag move from `teams` onto `users`, existing values
are copied to the user who signs in for each team, and `notification_logs` gains
`user_id` so a send keeps both its recipient and the team the event concerned.

Revision ID: 0002_notifications_by_user
Revises: 0001_initial
Create Date: 2026-10-08

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_notifications_by_user"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _users(as_left: bool = True) -> sa.Table:
    """The users table, spelled out so the batch rewrite never depends on reflection."""
    columns = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=300), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    ]
    constraints: list = [sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("username")]
    if not as_left:  # the schema after this migration
        columns[4:4] = [sa.Column("email", sa.String(length=254), nullable=True)]
        columns.insert(
            7,
            sa.Column("notify_email", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        )
        constraints.append(sa.UniqueConstraint("email", name="uq_users_email"))
    return sa.Table("users", sa.MetaData(), *columns, *constraints)


def _teams(as_left: bool = True) -> sa.Table:
    columns = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("calendar_token", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    ]
    constraints: list = [
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("calendar_token"),
    ]
    if as_left:  # the schema before this migration
        columns.insert(
            3,
            sa.Column("email", sa.String(length=254), nullable=True),
        )
        columns.append(sa.Column("notify_email", sa.Boolean(), nullable=False))
        constraints.append(sa.UniqueConstraint("email", name="email"))
    return sa.Table("teams", sa.MetaData(), *columns, *constraints)


def _notification_logs(as_left: bool = True) -> sa.Table:
    columns = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("recipient", sa.String(length=254), nullable=True),
        sa.Column("subject", sa.String(length=250), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
    ]
    constraints: list = [sa.PrimaryKeyConstraint("id")]
    team_fk = sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL")
    if as_left:
        constraints.append(team_fk)
    else:  # the schema after this migration
        columns.insert(
            2,
            sa.Column("user_id", sa.Integer(), nullable=True),
        )
        constraints.extend(
            [
                team_fk,
                sa.ForeignKeyConstraint(
                    ["user_id"], ["users.id"], name="fk_notification_logs_user_id", ondelete="SET NULL"
                ),
            ]
        )
    return sa.Table("notification_logs", sa.MetaData(), *columns, *constraints)


def upgrade() -> None:
    with op.batch_alter_table("users", copy_from=_users()) as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(length=254), nullable=True))
        batch_op.add_column(
            sa.Column("notify_email", sa.Boolean(), nullable=False, server_default=sa.text("1"))
        )
        batch_op.create_unique_constraint("uq_users_email", ["email"])

    with op.batch_alter_table("notification_logs", copy_from=_notification_logs()) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_notification_logs_user_id", "users", ["user_id"], ["id"], ondelete="SET NULL"
        )

    # Each address moves to the user who signs in for the team holding it; a user
    # covering several teams keeps the address of its lowest-numbered team, and the
    # addresses were already unique across teams, so the unique constraint holds.
    op.execute(
        """
        UPDATE users SET email = (
            SELECT t.email FROM teams t
            WHERE t.user_id = users.id AND t.email IS NOT NULL
            ORDER BY t.id LIMIT 1
        )
        WHERE EXISTS (
            SELECT 1 FROM teams t WHERE t.user_id = users.id AND t.email IS NOT NULL
        )
        """
    )
    # Notifications stay on unless every team of the user had them off.
    op.execute(
        """
        UPDATE users SET notify_email = 0
        WHERE EXISTS (SELECT 1 FROM teams t WHERE t.user_id = users.id)
          AND NOT EXISTS (
              SELECT 1 FROM teams t WHERE t.user_id = users.id AND t.notify_email = 1
          )
        """
    )
    # Old sends keep their team as context and gain the user who received them.
    op.execute(
        """
        UPDATE notification_logs SET user_id = (
            SELECT t.user_id FROM teams t WHERE t.id = notification_logs.team_id
        )
        WHERE team_id IS NOT NULL
        """
    )

    with op.batch_alter_table("teams", copy_from=_teams()) as batch_op:
        batch_op.drop_constraint("email", type_="unique")
        batch_op.drop_column("email")
        batch_op.drop_column("notify_email")


def downgrade() -> None:
    with op.batch_alter_table("notification_logs", copy_from=_notification_logs(as_left=False)) as batch_op:
        batch_op.drop_constraint("fk_notification_logs_user_id", type_="foreignkey")
        batch_op.drop_column("user_id")

    with op.batch_alter_table("teams", copy_from=_teams(as_left=False)) as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(length=254), nullable=True))
        batch_op.add_column(
            sa.Column("notify_email", sa.Boolean(), nullable=False, server_default=sa.text("1"))
        )
        batch_op.create_unique_constraint("email", ["email"])

    # Only the first team of each user can take the address back, or the unique
    # constraint on teams.email would refuse the second one.
    op.execute(
        """
        UPDATE teams SET email = (
            SELECT u.email FROM users u WHERE u.id = teams.user_id
        )
        WHERE user_id IS NOT NULL
          AND teams.id = (SELECT MIN(t.id) FROM teams t WHERE t.user_id = teams.user_id)
        """
    )
    op.execute(
        """
        UPDATE teams SET notify_email = (
            SELECT u.notify_email FROM users u WHERE u.id = teams.user_id
        )
        WHERE user_id IS NOT NULL
        """
    )

    with op.batch_alter_table("users", copy_from=_users(as_left=False)) as batch_op:
        batch_op.drop_constraint("uq_users_email", type_="unique")
        batch_op.drop_column("email")
        batch_op.drop_column("notify_email")
