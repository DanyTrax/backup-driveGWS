##
## SQL auth driver config
##
driver = pgsql
connect = host=${POSTGRES_HOST} port=${POSTGRES_PORT} dbname=${POSTGRES_DB} user=${POSTGRES_USER} password=${POSTGRES_PASSWORD}

default_pass_scheme = ARGON2ID

# Reads the argon2 hash from gw_accounts.imap_password_hash; only rows with
# imap_enabled = true and (imap_locked_until IS NULL OR imap_locked_until < now())
password_query = \
  SELECT email AS user, imap_password_hash AS password \
  FROM gw_accounts \
  WHERE email = '%u' \
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
  WHERE email = '%u'

iterate_query = SELECT email AS user FROM gw_accounts WHERE imap_enabled = TRUE
