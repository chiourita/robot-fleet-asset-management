FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /build

COPY app/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip cache purge

FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r robot && useradd -r -g robot robot

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

COPY app/ ./app/

RUN mkdir -p /app/configs /run/secrets /opt/robot/assets

COPY assets/ /opt/robot/assets/

RUN chown -R robot:robot /app && \
    chmod -R 755 /app && \
    chown -R robot:robot /opt/robot/assets && \
    chmod -R 755 /opt/robot/assets

# Switch to non-root user
USER robot

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
