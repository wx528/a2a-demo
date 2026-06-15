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
COPY web/ ./web/

CMD ["python", "web/main.py"]
