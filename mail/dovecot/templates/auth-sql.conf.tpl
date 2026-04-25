##
## SQL auth driver config
##
driver = pgsql
connect = host=${POSTGRES_HOST} port=${POSTGRES_PORT} dbname=${POSTGRES_DB} user=${POSTGRES_USER} password=${POSTGRES_PASSWORD}

# default_pass_scheme CRYPT: libcrypt con autodetección ($1$/$2a$/$5$/$6$). Más adecuado que
# SHA512-CRYPT para un $6$ crudo visto por el driver SQL. Legado $2$ sigue con CRYPT.
default_pass_scheme = CRYPT

# imap_password_hash: nuevas = {BLF-CRYPT}$2b$… (bcrypt). Legado: $6$ SHA512, {SHA512-CRYPT}$6$, argon2.
# Filas con imap_enabled = true y sin bloqueo.
# WHERE con lower() ya une la fila; el campo "user" devuelto debe coincidir con el login que
# envía IMAP (suele ser todo en minúsculas). Si devolvieras `email` tal cual (Google/Admin SDK
# a veces mezcla mayúsculas), passdb verifica el hash pero Dovecot descarta el login: auth failed.
password_query = \
  SELECT lower(email) AS user, TRIM(BOTH FROM imap_password_hash) AS password \
  FROM gw_accounts \
  WHERE lower(email) = lower('%u') \
    AND imap_enabled = TRUE \
    AND imap_password_hash IS NOT NULL \
    AND length(TRIM(BOTH FROM imap_password_hash)) > 10 \
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

iterate_query = SELECT lower(email) AS user FROM gw_accounts WHERE imap_enabled = TRUE
