FROM node:20-slim AS frontend

WORKDIR /app/frontend

COPY web/frontend/package.json web/frontend/package-lock.json ./
RUN npm ci
COPY web/frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

RUN pip install --no-cache-dir uv==0.5.9

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY shared/ ./shared/
COPY debate/personas.py debate/run_debate.py ./debate/
COPY web/main.py web/db.py web/turns.py ./web/
COPY --from=frontend /app/frontend/dist ./web/frontend/dist

CMD ["python", "web/main.py"]
