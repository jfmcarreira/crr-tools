from __future__ import annotations

import base64
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import PushSubscription
from .dependencies import _check_csrf, _require_user

router = APIRouter(prefix="/push")


class SubscriptionEndpoint(BaseModel):
    endpoint: str = Field(max_length=4096)

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        url = urlsplit(value)
        # Only browser push providers: never let subscriptions become an SSRF proxy.
        host = url.hostname or ""
        allowed = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com", "notify.windows.com")
        if (url.scheme != "https" or url.port not in (None, 443) or url.username
                or url.password or url.fragment or not any(host == name or host.endswith("." + name) for name in allowed)):
            raise ValueError("Endereço de notificações inválido")
        return value


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)

    @field_validator("p256dh", "auth")
    @classmethod
    def validate_key(cls, value: str, info) -> str:
        try:
            decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        except ValueError as exc:
            raise ValueError("Chave de notificações inválida") from exc
        if len(decoded) != (65 if info.field_name == "p256dh" else 16):
            raise ValueError("Chave de notificações inválida")
        return value


class SubscriptionPayload(SubscriptionEndpoint):
    keys: SubscriptionKeys


@router.post("/subscriptions")
def subscribe(payload: SubscriptionPayload, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    _check_csrf(request, request.headers.get("X-CSRF-Token", ""))
    if not settings.push_enabled:
        raise HTTPException(503, "As notificações ainda não estão configuradas")
    subscription = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint))
    if subscription is not None and subscription.user_id != user.id:
        raise HTTPException(409, "Desativa as notificações da conta anterior neste dispositivo antes de as ativar")
    if subscription is None:
        subscription = PushSubscription(user_id=user.id, endpoint=payload.endpoint)
        db.add(subscription)
    subscription.p256dh = payload.keys.p256dh
    subscription.auth = payload.keys.auth
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Não foi possível guardar a subscrição. Tenta novamente.")
    return {"enabled": True}


@router.delete("/subscriptions")
def unsubscribe(payload: SubscriptionEndpoint, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    _check_csrf(request, request.headers.get("X-CSRF-Token", ""))
    subscription = db.scalar(select(PushSubscription).where(
        PushSubscription.endpoint == payload.endpoint, PushSubscription.user_id == user.id,
    ))
    if subscription is not None:
        db.delete(subscription)
        db.commit()
    return {"enabled": False}
