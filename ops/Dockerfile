FROM node:22-alpine AS web-build

WORKDIR /app

COPY package.json package-lock.json ./
COPY frontend/web/package.json ./frontend/web/package.json
RUN npm ci

COPY frontend/web ./frontend/web
RUN npm run web:build


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY backend/src ./backend/src
COPY backend/alembic.ini ./backend/alembic.ini
COPY backend/migrations ./backend/migrations
COPY --from=web-build /app/frontend/web/dist ./backend/src/onebrain_web/react_build

RUN uv sync --frozen --no-dev --no-editable

EXPOSE 8000

CMD ["onebrain-host"]
