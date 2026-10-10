from sqlalchemy.orm import Session

from ..models import NotificationSetting

MASTER_SETTING_KEY = ("__master__", "all")


def notification_enabled(db: Session) -> bool:
    """One delivery gate, independent of users' preferences and subscriptions."""
    setting = db.get(NotificationSetting, MASTER_SETTING_KEY, populate_existing=True)
    return setting is None or setting.enabled
