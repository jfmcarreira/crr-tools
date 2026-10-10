"""Persist global notification delivery preferences."""

from alembic import op
import sqlalchemy as sa

revision = "0007_notification_settings"
down_revision = "0006_push_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No rows initially: all existing event/channel combinations remain enabled.
    op.create_table(
        "notification_settings",
        sa.Column("event_type", sa.String(60), primary_key=True),
        sa.Column("channel", sa.String(20), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notification_settings")
