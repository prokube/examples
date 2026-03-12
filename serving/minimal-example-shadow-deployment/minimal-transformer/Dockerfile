FROM python:3.12-slim

WORKDIR /app

# Installing necessary build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY ./pyproject.toml . 
RUN pip install .

COPY main.py .
COPY PredictionDBHandler.py .

ENTRYPOINT ["python", "main.py"]
