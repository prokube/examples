# Use Python 3.12 as base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install uv for package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Copy project files
COPY pyproject.toml README.md ./
COPY pipe_fiction/ ./pipe_fiction/

# Install the package with uv
RUN uv pip install --system -e .

# Set Python path
ENV PYTHONPATH=/app
