# 使用 uv 多阶段构建
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# 安装 uv
RUN pip install --no-cache-dir uv==0.5.9

# 复制依赖描述文件，利用 Docker 缓存
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# 运行阶段使用精简镜像
FROM python:3.11-slim

WORKDIR /app

# 从 builder 复制虚拟环境
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# 复制应用代码
COPY shared/ ./shared/
COPY research_agent/ ./research_agent/

CMD ["python", "research_agent/main.py"]
