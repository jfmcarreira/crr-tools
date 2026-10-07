from fastapi import APIRouter, Request, Response
from pydantic import Field, field_validator

from ..errors import AppError
from ..schemas.base import RequestSchema
from ..security.session import COOKIE_NAME, create_token, password_matches, valid_token

router = APIRouter(prefix="/api/auth")


class LoginInput(RequestSchema):
    password: str = Field(strict=True, min_length=1, max_length=1000)

    @field_validator("password")
    @classmethod
    def password_length(cls, value):
        if len(value.encode("utf-16-le", errors="surrogatepass")) // 2 > 1000:
            raise ValueError("Invalid password length")
        return value


@router.post("/login")
def login(body: LoginInput, request: Request, response: Response):
    # Checking, recording and resetting attempts must be atomic across ASGI workers.
    with request.app.state.limiter.lock:
        return finish_login(body, request, response)


def finish_login(body: LoginInput, request: Request, response: Response):
    settings, limiter = request.app.state.settings, request.app.state.limiter
    key = request.client.host if request.client else ""
    if limiter.limited(key):
        raise AppError(429, "Foram feitas demasiadas tentativas. Tente novamente mais tarde.")
    if not password_matches(body.password, settings.admin_password):
        limiter.failure(key)
        raise AppError(401, "A palavra-passe está incorreta.")
    limiter.clear(key)
    response.set_cookie(COOKIE_NAME, create_token(settings), path=settings.app_base_path,
                        httponly=True, samesite="strict", secure=request.url.scheme == "https",
                        max_age=settings.session_lifetime_ms // 1000)
    return {"authenticated": True}


@router.post("/logout")
def logout(request: Request, response: Response):
    response.delete_cookie(COOKIE_NAME, path=request.app.state.settings.app_base_path,
                           httponly=True, samesite="strict", secure=request.url.scheme == "https")
    return {"authenticated": False}


@router.get("/session")
@router.head("/session", include_in_schema=False)
def session(request: Request):
    return {"authenticated": valid_token(request.cookies.get(COOKIE_NAME), request.app.state.settings)}
