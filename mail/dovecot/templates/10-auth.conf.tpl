##
## Auth backend: SQL (Postgres) + master user (admin SSO)
##
disable_plaintext_auth = no
auth_mechanisms = plain login

passdb {
  driver = sql
  args = /etc/dovecot/conf.d/auth-sql.conf
}

userdb {
  driver = sql
  args = /etc/dovecot/conf.d/auth-sql.conf
}

# Master passdb — admin of the platform impersonates any user without knowing their password.
passdb {
  driver = passwd-file
  master = yes
  args = /etc/dovecot/conf.d/master-users
  # Result format lines look like:   user:{SCHEME}hash
}
