FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir uv==0.9.5 \
    && useradd --create-home --uid 10001 clef

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra model --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev --extra model

ENV PATH="/app/.venv/bin:$PATH"

USER 10001

EXPOSE 8080

CMD ["uvicorn", "clef_server.app:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
