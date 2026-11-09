# Bookworm and a uv-managed Python: the agent sandbox snapshots and restores
# the running process, which the system Python of newer bases does not survive.
FROM ghcr.io/astral-sh/uv:0.12.3 AS uv

FROM debian:bookworm-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_PREFERENCE=only-managed UV_PYTHON_INSTALL_DIR=/python UV_COMPILE_BYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/
RUN uv venv --python 3.13 /app/.venv \
    && VIRTUAL_ENV=/app/.venv uv pip install --no-cache -r /app/requirements.txt

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir /config && chown 65532:65532 /config
COPY --from=build /python /python
COPY --from=build /app/.venv /app/.venv
COPY agent.py server.py /app/
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /app
USER 65532:65532
ENTRYPOINT ["python", "server.py"]
