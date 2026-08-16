# ── Stage 1: Build ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

COPY pyproject.toml .
COPY hive/ hive/
RUN pip install --no-cache-dir --prefix=/install -e .

# ── Stage 2: Runtime ────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="Marko Gorny <sockagorny@gmail.com>"
LABEL description="Hive — Self-hosted Multi-Agent AI Platform"
LABEL version="1.0.0"

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY pyproject.toml .
COPY hive/ hive/
COPY main.py .
COPY static/ static/

# Create data directories
RUN mkdir -p keystore relay_mailbox uploads skills hive_memory workspace_files

# Non-root user for security
RUN groupadd -r hive && useradd -r -g hive -d /app -s /sbin/nologin hive
RUN chown -R hive:hive /app
USER hive

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

# HTTP API + P2P UDP
EXPOSE 8000
EXPOSE 4242/udp

# Run as non-root
CMD ["uvicorn", "hive.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]
