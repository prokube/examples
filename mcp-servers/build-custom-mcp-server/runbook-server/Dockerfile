FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RUNBOOK_DIR=/data/runbooks \
    SEED_RUNBOOK_DIR=/app/seed-runbooks

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py ./server.py
COPY seed-runbooks ./seed-runbooks

RUN useradd --create-home --uid 10001 appuser
USER 10001

ENTRYPOINT ["python", "server.py"]
