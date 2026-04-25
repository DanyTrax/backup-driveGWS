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
# Si la .tpl en el contenedor no trae el separador: suele ser bind-mount viejo en /etc/dovecot/templates.
if ! grep -qF 'auth_master_user_separator' /etc/dovecot/templates/10-auth.conf.tpl 2>/dev/null; then
  echo "[dovecot-entrypoint] 10-auth.conf.tpl no trae auth_master_user_separator. Causa típica: volumen o bind en /etc/dovecot (docker inspect msa-backup-dovecot -> Mounts). Quita ese mount en Dockge/compose y recrea; el repo solo monta maildirs en /var/mail/vhosts. .tpl:" >&2
  head -25 /etc/dovecot/templates/10-auth.conf.tpl 2>&1 | sed 's/^/[tpl] /' >&2
  exit 1
fi
cat /etc/dovecot/templates/10-auth.conf.tpl > /etc/dovecot/conf.d/10-auth.conf
chmod 600 /etc/dovecot/conf.d/10-auth.conf
# Solo ${POSTGRES_*}; con envsubst "total", los $ de comentarios/argon2/bcrypt se comen a "".
envsubst '$POSTGRES_HOST $POSTGRES_PORT $POSTGRES_DB $POSTGRES_USER $POSTGRES_PASSWORD' \
  < /etc/dovecot/templates/auth-sql.conf.tpl > /etc/dovecot/conf.d/auth-sql.conf
chmod 600 /etc/dovecot/conf.d/auth-sql.conf

if ! LC_ALL=C grep -qF 'auth_master_user_separator' /etc/dovecot/conf.d/10-auth.conf 2>/dev/null; then
  echo "[dovecot-entrypoint] 10-auth.conf generado no contiene auth_master_user_separator. debug:" >&2
  echo "[dovecot-entrypoint] bytes tpl=$(wc -c < /etc/dovecot/templates/10-auth.conf.tpl) out=$(wc -c < /etc/dovecot/conf.d/10-auth.conf)" >&2
  head -25 /etc/dovecot/conf.d/10-auth.conf 2>&1 | sed 's/^/[out] /' >&2
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
