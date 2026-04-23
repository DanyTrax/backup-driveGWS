#!/usr/bin/env bash
# Multi-role entrypoint for the backend image.
# ROLE env decides which process to run (api | worker | beat).
set -euo pipefail

ROLE="${ROLE:-api}"
cd /app

wait_for_postgres() {
  echo "[entrypoint] waiting for Postgres..."
  python - <<'PY'
import os, time, sys, socket
host = os.environ.get("POSTGRES_HOST", "postgres")
port = int(os.environ.get("POSTGRES_PORT", "5432"))
for _ in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            sys.exit(0)
    except OSError:
        time.sleep(2)
print("Postgres not reachable, aborting", file=sys.stderr)
sys.exit(1)
PY
}

wait_for_redis() {
  echo "[entrypoint] waiting for Redis..."
  python - <<'PY'
import os, time, sys, socket
host = os.environ.get("REDIS_HOST", "redis")
port = int(os.environ.get("REDIS_PORT", "6379"))
for _ in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            sys.exit(0)
    except OSError:
        time.sleep(2)
print("Redis not reachable, aborting", file=sys.stderr)
sys.exit(1)
PY
}

run_migrations() {
  echo "[entrypoint] running alembic migrations..."
  alembic upgrade head || {
    echo "[entrypoint] alembic upgrade failed — continuing anyway (bootstrap phase)"
  }
}

case "${ROLE}" in
  api)
    wait_for_postgres
    wait_for_redis
    run_migrations
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
    ;;
  worker)
    wait_for_postgres
    wait_for_redis
    exec celery -A app.workers.celery_app worker --loglevel=INFO --concurrency="${CELERY_CONCURRENCY:-2}"
    ;;
  beat)
    wait_for_postgres
    wait_for_redis
    exec celery -A app.workers.celery_app beat --loglevel=INFO --schedule=/data/celerybeat-schedule
    ;;
  bash|sh)
    exec bash
    ;;
  *)
    exec "$@"
    ;;
esac
