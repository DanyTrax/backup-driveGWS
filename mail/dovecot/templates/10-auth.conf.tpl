##
## Auth backend: SQL (Postgres) + master user (admin SSO)
##
# Orden: TODOS los passdb (SQL y luego master) ANTES de cualquier userdb. Si `userdb` queda
# entre medias, el passdb `master` no se aplica bien y "usuario*..." falla aunque master-users esté ok.
#
disable_plaintext_auth = no
auth_mechanisms = plain login
auth_master_user_separator = *

passdb {
  driver = sql
  args = /etc/dovecot/conf.d/auth-sql.conf
}

# Master passdb — admin of the platform impersonates any user without knowing their password.
passdb {
  driver = passwd-file
  master = yes
  args = /etc/dovecot/conf.d/master-users
}

# El passdb SQL devuelve userdb_* en el mismo query (password_query). IMAP rellena con prefetch;
# sin esto, el userdb { sql } corre user_query y un fallo ahí mata el login aunque el hash fuese bueno.
userdb {
  driver = prefetch
}
userdb {
  driver = sql
  args = /etc/dovecot/conf.d/auth-sql.conf
}
