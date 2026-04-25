##
## SQL auth driver config
##
driver = pgsql
connect = host=${POSTGRES_HOST} port=${POSTGRES_PORT} dbname=${POSTGRES_DB} user=${POSTGRES_USER} password=${POSTGRES_PASSWORD}

# Valor por defecto solo aplica si el hash en BD no trae esquema explícito; $argon2id$ / $2b$ / {BLF-CRYPT} se autodetectan.
default_pass_scheme = BLF-CRYPT

# `imap_password_hash`: bcrypt como `$2a$` / `$2b$` (recomendado) o con prefijo {BLF-CRYPT} legado; argon2 legado.
# Filas con imap_enabled = true y sin bloqueo.
# email con lower(): evita fallo si la BD trae mezcla de mayúsculas (API Google) y el usuario
# escribe en minúsculas en Roundcube (Postgres: = '%u' es sensible a mayúsculas).
password_query = \
  SELECT email AS user, TRIM(BOTH FROM imap_password_hash) AS password \
  FROM gw_accounts \
  WHERE lower(email) = lower('%u') \
    AND imap_enabled = TRUE \
    AND (imap_locked_until IS NULL OR imap_locked_until < now())

# User is resolved into a Maildir path built from the account record.
user_query = \
  SELECT \
    5000 AS uid, \
    5000 AS gid, \
    COALESCE(maildir_path, '/var/mail/vhosts/' || split_part(email, '@', 2) || '/' || split_part(email, '@', 1)) AS home, \
    'maildir:' || COALESCE(maildir_path, '/var/mail/vhosts/' || split_part(email, '@', 2) || '/' || split_part(email, '@', 1)) || '/Maildir' AS mail \
  FROM gw_accounts \
  WHERE lower(email) = lower('%u')

iterate_query = SELECT email AS user FROM gw_accounts WHERE imap_enabled = TRUE
