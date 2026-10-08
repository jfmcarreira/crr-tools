from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .services.bootstrap import ensure_initial_data
from .branding import BRAND_DIR
from .config import settings
from .database import (
    SessionLocal,
    backup_database,
    run_migrations,
)
from .i18n import (
    day_long,
    day_numeric,
    day_numeric_long,
    day_short,
    event_type_label,
    moment,
    notification_status_label,
    source_label,
    swap_status_label,
    weekday_name,
    window_label,
)
from .routers import router
from .security.rate_limit import LoginRateLimiter

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A copy of the database before anything else runs; never fatal.
    try:
        backup = backup_database()
        if backup is not None:
            print(f"Database backup written to {backup}")
    except Exception as exc:  # a failed backup must never stop the app
        print(f"Could not back up the database: {exc}")
    run_migrations()
    with SessionLocal() as db:
        ensure_initial_data(db)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan, root_path=settings.root_path)
# In-process counter of failed logins; see security/rate_limit.py for the limits.
app.state.limiter = LoginRateLimiter()
app.state.registration_limiter = LoginRateLimiter(maximum_failures=5, window_seconds=300)
# Behind a reverse proxy, uvicorn runs with --proxy-headers so X-Forwarded-Proto/Host
# set the public scheme and host; ROOT_PATH adds the prefix the proxy serves us under.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    same_site="lax",
    https_only=settings.session_https_only,
    max_age=60 * 60 * 24 * 30,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/brand", StaticFiles(directory=BRAND_DIR), name="brand")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.filters.update(
    {
        "dia": day_short,
        "dia_curto": lambda day: weekday_name(day.weekday(), short=True),
        "dia_longo": day_long,
        "data": day_numeric,
        "data_longa": day_numeric_long,
        "momento": moment,
        "origem": source_label,
        "estado": swap_status_label,
        "estado_email": notification_status_label,
        "evento": event_type_label,
        "horario": lambda schedule: window_label(schedule.start_time, schedule.end_time),
    }
)
templates.env.globals["app_path"] = settings.url
app.state.templates = templates
app.include_router(router)
