#!/usr/bin/env bash
set -e

ENV=${1:-dev}

echo "Running database migrations..."
alembic upgrade head

echo "Seeding database..."
python seed.py

PORT="${PORT:-8000}"
echo "Starting application in $ENV mode on port $PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
