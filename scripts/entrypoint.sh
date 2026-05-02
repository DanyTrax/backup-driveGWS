#!/usr/bin/env bash
# Multi-role entrypoint for the backend image.
# ROLE env decides which process to run (api | worker | beat).
set -euo pipefail

ROLE="${ROLE:-api}"
cd /app

# Volumen compartido app/worker/dovecot: permisos para crear Maildir aunque el volumen
# se cree con otro propietario (p. ej. dovecot en el primer arranque).
prepare_maildir_volume() {
  mkdir -p /var/mail/vhosts
  chmod 0777 /var/mail/vhosts 2>/dev/null || true
}

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
  alembic upgrade head
}

verify_app_import() {
  echo "[entrypoint] verifying FastAPI app import (si falla: código en /app/app o .env inválido)..."
  python -c "import app.main; print('[entrypoint] app.main import OK')"
}

case "${ROLE}" in
  api)
    prepare_maildir_volume
    wait_for_postgres
    wait_for_redis
    run_migrations
    verify_app_import
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
    ;;
  worker)
    wait_for_postgres
    wait_for_redis
    exec celery -A app.workers.celery_app worker --loglevel=INFO --concurrency="${CELERY_CONCURRENCY:-2}"
    ;;
  beat)
    prepare_maildir_volume
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
