FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt ./app_requirements.txt
COPY dashboard/requirements.txt ./dashboard_requirements.txt
RUN pip install --no-cache-dir -r app_requirements.txt -r dashboard_requirements.txt

COPY app/ ./app/
COPY dashboard/ ./dashboard/
COPY start.sh ./start.sh

RUN mkdir -p /app/logs && useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["./start.sh"]
