FROM ghcr.io/astral-sh/uv:0.11.31 AS uv
FROM python:3.13-slim
COPY --from=uv /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"
WORKDIR /workspace
COPY pyproject.toml uv.lock ./
COPY apps/shifts/backend/pyproject.toml apps/shifts/backend/pyproject.toml
COPY apps/tournament/backend/pyproject.toml apps/tournament/backend/pyproject.toml
COPY packages/crr-python/ packages/crr-python/
COPY packages/ttlock/ packages/ttlock/
RUN uv sync --frozen --package crr-shifts --no-dev --no-editable
COPY apps/shifts/backend/ apps/shifts/backend/
COPY packages/crr-brand/ packages/crr-brand/
WORKDIR /workspace/apps/shifts/backend
# Non-root like Tournament; /data matches the named volume, data/ is the
# in-container default database location for runs without compose.
RUN groupadd --gid 1000 shifts && useradd --uid 1000 --gid 1000 --no-create-home shifts \
    && mkdir -p data /data && chown -R shifts:shifts data /data
USER shifts
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
