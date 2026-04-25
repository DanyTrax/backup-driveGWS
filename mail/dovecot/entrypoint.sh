#!/usr/bin/env bash
# Renders templated configs with envsubst, waits for Postgres, then exec dovecot.
set -euo pipefail

echo "[dovecot-entrypoint] rendering config from templates..."
# Asegurar no heredar 10-auth de capas viejas o de la base si el build estuvo mal.
rm -f /etc/dovecot/conf.d/10-auth.conf /etc/dovecot/conf.d/auth-sql.conf
if [ ! -f /etc/dovecot/templates/10-auth.conf.tpl ] || [ ! -f /etc/dovecot/templates/auth-sql.conf.tpl ]; then
  echo "[dovecot-entrypoint] faltan plantillas en /etc/dovecot/templates (reconstruir imagen: COPY templates/ vacío?)" >&2
  exit 1
fi
for tpl in /etc/dovecot/templates/*.tpl; do
  [ -f "$tpl" ] || continue
  # master-users NUNCA con envsubst: las contraseñas con $ (y otros) se corrompen.
  bname=$(basename "${tpl}" .tpl)
  if [ "$bname" = "master-users" ]; then
    continue
  fi
  out="/etc/dovecot/conf.d/${bname}"
  # 10-auth: sin $ → cat (evita envsubst al estilo "total" y diferencias de gettext con el entorno).
  # auth-sql: solo ${POSTGRES_*}; si no, $argon2id$ / $2b$ en comentarios o en hashes se comen a "".
  if [ "$bname" = "10-auth.conf" ]; then
    cat "${tpl}" > "${out}"
  elif [ "$bname" = "auth-sql.conf" ]; then
    envsubst '$POSTGRES_HOST $POSTGRES_PORT $POSTGRES_DB $POSTGRES_USER $POSTGRES_PASSWORD' < "${tpl}" > "${out}"
  else
    envsubst < "${tpl}" > "${out}"
  fi
  chmod 600 "${out}"
done

if ! grep -q 'auth_master_user_separator' /etc/dovecot/conf.d/10-auth.conf 2>/dev/null; then
  echo "[dovecot-entrypoint] 10-auth.conf no es el esperado (falta auth_master_user_separator). Revisa plantilla o imagen." >&2
  exit 1
fi

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
