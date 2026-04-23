#!/usr/bin/env bash
# Renders templated configs with envsubst, waits for Postgres, then exec dovecot.
set -euo pipefail

echo "[dovecot-entrypoint] rendering config from templates..."
for tpl in /etc/dovecot/templates/*.tpl; do
  out="/etc/dovecot/conf.d/$(basename "${tpl}" .tpl)"
  envsubst < "${tpl}" > "${out}"
  chmod 600 "${out}"
done

echo "[dovecot-entrypoint] waiting for Postgres at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
until PGPASSWORD="${POSTGRES_PASSWORD}" psql \
      -h "${POSTGRES_HOST}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
      -c 'SELECT 1' >/dev/null 2>&1; do
  sleep 2
done
echo "[dovecot-entrypoint] Postgres is up. Starting Dovecot."

exec "$@"
