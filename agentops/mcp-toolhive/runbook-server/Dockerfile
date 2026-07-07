FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RUNBOOK_DIR=/data/runbooks

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py ./server.py

RUN useradd --create-home --uid 10001 appuser
USER 10001

ENTRYPOINT ["python", "server.py"]
