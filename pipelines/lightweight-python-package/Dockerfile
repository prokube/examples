FROM python:3.11-slim

WORKDIR /app

# Upgrade pip for better timeout handling
RUN pip install --upgrade pip

# Copy and install the package with retries for slow connections
COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir --default-timeout=300 --retries=5 .
