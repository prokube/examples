FROM python:3.12-slim

ENV HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py server.py agent-card.json ./

RUN useradd --create-home --uid 10001 appuser
USER 10001

EXPOSE 8080
ENTRYPOINT ["python", "server.py"]
