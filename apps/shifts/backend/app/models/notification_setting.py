from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class NotificationSetting(Base):
    """Delivery settings; the (__master__, all) row is the global delivery gate."""

    __tablename__ = "notification_settings"

    event_type: Mapped[str] = mapped_column(String(60), primary_key=True)
    channel: Mapped[str] = mapped_column(String(20), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
