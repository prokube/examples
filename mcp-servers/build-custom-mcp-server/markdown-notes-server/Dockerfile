FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    NOTE_DIR=/data/notes \
    SEED_NOTE_DIR=/app/seed-notes

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py ./server.py
COPY seed-notes ./seed-notes

RUN useradd --create-home --uid 10001 appuser
USER 10001

ENTRYPOINT ["python", "server.py"]
