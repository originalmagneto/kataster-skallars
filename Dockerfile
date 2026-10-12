FROM ghcr.io/astral-sh/uv:0.6.5@sha256:562193a4a9d398f8aedddcb223e583da394ee735de36b5815f8f1d22cb49be15 AS uv
FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable && useradd --uid 10001 --create-home kataster && mkdir /data && chown kataster /data
USER 10001:10001
ENV PATH="/app/.venv/bin:$PATH" SK_KATASTER_DATA_DIR=/data
EXPOSE 8000
CMD ["kataster-http"]
