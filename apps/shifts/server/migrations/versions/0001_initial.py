"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("schedule_type", sa.String(length=20), nullable=False),
        sa.Column("weekdays", sa.String(length=30), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("requires_manager_approval", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("rotation_anchor_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    # A user is a login: one username, several teams can be assigned to it.
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=300), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    # A team is who works a shift; without a user nobody signs in for it.
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("calendar_token", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notify_email", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("calendar_token"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("schedule_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("schedule_id", "date", name="uq_assignment_schedule_date"),
    )
    with op.batch_alter_table("assignments", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_assignments_date"), ["date"], unique=False)

    op.create_table(
        "monthly_patterns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("schedule_id", sa.Integer(), nullable=False),
        sa.Column("day_of_month", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("day_of_month BETWEEN 1 AND 31", name="ck_pattern_day_of_month"),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("schedule_id", "day_of_month", name="uq_pattern_schedule_day"),
    )
    op.create_table(
        "notification_logs",
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
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rotation_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("schedule_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("schedule_id", "position", name="uq_rotation_schedule_position"),
        sa.UniqueConstraint("schedule_id", "team_id", name="uq_rotation_schedule_team"),
    )
    op.create_table(
        "swap_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("target_assignment_id", sa.Integer(), nullable=True),
        sa.Column("requester_id", sa.Integer(), nullable=False),
        sa.Column("target_team_id", sa.Integer(), nullable=True),
        sa.Column("accepted_team_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["accepted_team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_assignment_id"], ["assignments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("swap_requests")
    op.drop_table("rotation_members")
    op.drop_table("notification_logs")
    op.drop_table("monthly_patterns")
    with op.batch_alter_table("assignments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_assignments_date"))

    op.drop_table("assignments")
    op.drop_table("teams")
    op.drop_table("users")
    op.drop_table("schedules")