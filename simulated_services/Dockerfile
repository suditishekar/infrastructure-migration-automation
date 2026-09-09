# Minimal, dependency-free HTTP stub image reused for every simulated
# legacy service in docker-compose.yml (behavior configured via env vars,
# see server.py). No external packages required.

FROM python:3.11-alpine

WORKDIR /app
COPY server.py .

HEALTHCHECK --interval=5s --timeout=3s --start-period=3s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.environ.get('PORT', '8080') + os.environ.get('HEALTH_PATH', '/health'), timeout=2)" || exit 1

CMD ["python", "server.py"]
