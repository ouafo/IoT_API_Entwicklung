FROM python:3.12-slim

WORKDIR /app

# Reduce noisy output and pip version checks
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY app/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code into /app/app
COPY app/ ./app/

# Create logs directory
RUN mkdir -p /app/logs

# Create non-root user and set ownership
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check (uses httpx from requirements)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys, httpx; r = httpx.get('http://localhost:8000/health', timeout=5); sys.exit(0 if r.status_code == 200 else 1)"

# Run application (package import to ensure module resolution)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
