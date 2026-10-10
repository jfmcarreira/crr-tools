FROM node:22-alpine AS frontend
WORKDIR /workspace/apps/tournament/frontend
COPY apps/tournament/frontend/package.json apps/tournament/frontend/package-lock.json ./
RUN npm ci
COPY apps/tournament/frontend/ ./
COPY packages/crr-brand/ /workspace/packages/crr-brand/
ARG VITE_BASE_PATH=/jogo/
ENV VITE_BASE_PATH=${VITE_BASE_PATH}
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.11.31 AS uv
FROM python:3.13-slim AS runtime
COPY --from=uv /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH" DATABASE_PATH=/data/tournament.sqlite APP_BASE_PATH=/jogo/
WORKDIR /workspace
COPY pyproject.toml uv.lock ./
COPY apps/tournament/backend/pyproject.toml apps/tournament/backend/pyproject.toml
COPY apps/shifts/server/pyproject.toml apps/shifts/server/pyproject.toml
COPY packages/crr-python/ packages/crr-python/
COPY packages/ttlock/pyproject.toml packages/ttlock/pyproject.toml
RUN uv sync --frozen --package crr-tournament --no-dev --no-editable
COPY apps/tournament/backend/ apps/tournament/backend/
COPY --from=frontend /workspace/apps/tournament/frontend/dist apps/tournament/frontend/dist/
RUN groupadd --gid 1000 tournament && useradd --uid 1000 --gid 1000 --no-create-home tournament && mkdir /data && chown tournament /data
WORKDIR /workspace/apps/tournament/backend
USER tournament
EXPOSE 8080
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-proxy-headers"]
