# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gcc build-essential && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 --retries 10 -r requirements.txt

# Stage 2: Runtime Base
FROM python:3.11-slim AS runtime-base
WORKDIR /app

# Install runtime dependencies for Docling (OCR / PDF parsing)
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libxcb1 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Stage 3: Development
FROM runtime-base AS development
COPY . .

RUN chmod +x /app/start.sh
RUN mkdir -p data/temp logs

EXPOSE 8000

# Run in development mode
CMD ["/app/start.sh", "dev"]

# Stage 4: Production
FROM runtime-base AS production
COPY . .

RUN chmod +x /app/start.sh
RUN mkdir -p data/temp logs

EXPOSE 8000

# Run in production mode
CMD ["/app/start.sh", "prod"]
