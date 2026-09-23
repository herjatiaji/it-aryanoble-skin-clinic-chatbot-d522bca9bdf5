#!/usr/bin/env bash
set -e

ENV=${1:-dev}

echo "Running database migrations..."
alembic upgrade head

echo "Seeding database..."
python seed.py

PORT="${PORT:-8000}"
WORKERS="${WORKERS:-2}"

echo "Starting application in $ENV mode on port $PORT with $WORKERS worker(s)..."
if [ "$ENV" = "dev" ] || [ "$ENV" = "development" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload --reload-dir app
else
    exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers "$WORKERS"
fi

