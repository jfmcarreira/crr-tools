import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from sqlalchemy.orm import sessionmaker
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from .config import Settings
from .database import create_database_engine, run_migrations
from .errors import AppError, install_errors
from .events import StateChangeEvents
from .routers import auth, public
from .routers.admin import calendar, display, final_stage, groups, matches, settings as settings_router, teams
from .security.rate_limit import LoginRateLimiter


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = create_database_engine(settings.database_path)
    events = StateChangeEvents()

    @asynccontextmanager
    async def lifespan(app):
        try:
            run_migrations(engine)
            yield
        finally:
            events.close()
            engine.dispose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = sessionmaker(engine, expire_on_commit=False)
    app.state.database_lock = asyncio.Lock()
    app.state.events = events
    app.state.limiter = LoginRateLimiter()
    if settings.trust_proxy:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    install_errors(app)
    for router in [auth.router, public.router, settings_router.router, display.router, groups.router,
                   teams.router, calendar.router, matches.router, final_stage.router]:
        app.include_router(router)

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def client(path: str):
        root = settings.client_dist_path.resolve()
        file = (root / path).resolve()
        if not file.is_relative_to(root):
            raise AppError(404, "O recurso pedido não existe.")
        if path in ("", "results", "display", "display/", "admin") or path.startswith("admin/"):
            file = root / "index.html"
        if not file.is_file():
            raise AppError(404, "O recurso pedido não existe.")
        return FileResponse(file)

    return app
