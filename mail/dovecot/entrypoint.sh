#!/usr/bin/env bash
# Renders templated configs with envsubst, waits for Postgres, then exec dovecot.
set -euo pipefail

echo "[dovecot-entrypoint] rendering config from templates..."
for tpl in /etc/dovecot/templates/*.tpl; do
  [ -f "$tpl" ] || continue
  # master-users NUNCA con envsubst: las contraseñas con $ (y otros) se corrompen.
  bname=$(basename "${tpl}" .tpl)
  if [ "$bname" = "master-users" ]; then
    continue
  fi
  out="/etc/dovecot/conf.d/${bname}"
  envsubst < "${tpl}" > "${out}"
  chmod 600 "${out}"
done

musers="/etc/dovecot/conf.d/master-users"
: "${DOVECOT_MASTER_USER:=backup_admin_master}"
if [ -z "${DOVECOT_MASTER_PASSWORD:-}" ]; then
  echo "[dovecot-entrypoint] DOVECOT_MASTER_PASSWORD no está definido (hace falta para admin SSO y passdb master)." >&2
  exit 1
fi
umask 077
# printf evita intérpretes de $ respecto a envsubst; único salto al final
printf '%s\n' "${DOVECOT_MASTER_USER}:{PLAIN}${DOVECOT_MASTER_PASSWORD}" > "${musers}"
chmod 600 "${musers}"

echo "[dovecot-entrypoint] waiting for Postgres at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
until PGPASSWORD="${POSTGRES_PASSWORD}" psql \
      -h "${POSTGRES_HOST}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
      -c 'SELECT 1' >/dev/null 2>&1; do
  sleep 2
done
echo "[dovecot-entrypoint] Postgres is up. Starting Dovecot."

exec "$@"
