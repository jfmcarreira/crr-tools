from sqlalchemy.orm import Session

from ..models import NotificationSetting

MASTER_SETTING_KEY = ("__master__", "all")
NOTIFICATION_CHANNELS = ("email", "push")


def notification_enabled(db: Session, channel: str) -> bool:
    """A global gate per channel; inherit the legacy switch until first saved."""
    if channel not in NOTIFICATION_CHANNELS:
        raise ValueError("Canal de notificação inválido")
    setting = db.get(NotificationSetting, (MASTER_SETTING_KEY[0], channel), populate_existing=True)
    if setting is None:
        setting = db.get(NotificationSetting, MASTER_SETTING_KEY, populate_existing=True)
    return setting is None or setting.enabled
