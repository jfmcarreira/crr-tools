from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from ..errors import AppError
from ..security.session import COOKIE_NAME, valid_token


async def get_db(request: Request):
    # The Node backend executed each synchronous SQLite operation serially.
    # Preserve that behavior for read/modify/write operations such as automatic numbering.
    async with request.app.state.database_lock:
        with request.app.state.sessions() as db:
            yield db


DB = Annotated[Session, Depends(get_db)]


def require_admin(request: Request) -> None:
    if not valid_token(request.cookies.get(COOKIE_NAME), request.app.state.settings):
        raise AppError(401, "É necessário iniciar sessão para aceder à administração.")


def changed(db: Session, request: Request) -> None:
    db.commit()
    request.app.state.events.broadcast()


def confirm(value: bool, message: str) -> None:
    if not value:
        raise AppError(409, message)
