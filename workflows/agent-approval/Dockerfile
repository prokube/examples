FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir \
    "prokube-sdk[workflows] @ git+https://github.com/prokube/prokube-sdk@feature/workflows-keycloak-login"
WORKDIR /app
COPY activities.py workflows.py worker.py ./
USER 1000
CMD ["python", "worker.py"]
