# =====================================================================
# Dovecot interno con auth SQL (Postgres) + master user
# Solo expuesto en red Docker interna (no al host).
# =====================================================================

FROM dovecot/dovecot:2.3

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      postgresql-client gettext-base ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Config files (rendered from templates at entrypoint with envsubst)
COPY conf.d/ /etc/dovecot/conf.d/
COPY templates/ /etc/dovecot/templates/
COPY entrypoint.sh /usr/local/bin/dovecot-entrypoint.sh
# La base dovecot/dovecot trae 10-auth.conf, etc. COPY hace MERGE: lo que no está en
# conf.d/ del repo permanece. Si faltan *.tpl en el contexto, el entrypoint no pisa
# esos archivos y queda un orden de auth roto. Borramos los que generamos desde *.tpl.
RUN set -eux; \
  test -s /etc/dovecot/templates/10-auth.conf.tpl; \
  test -s /etc/dovecot/templates/auth-sql.conf.tpl; \
  grep -q 'auth_master_user_separator' /etc/dovecot/templates/10-auth.conf.tpl; \
  rm -f /etc/dovecot/conf.d/10-auth.conf /etc/dovecot/conf.d/auth-sql.conf
RUN chmod +x /usr/local/bin/dovecot-entrypoint.sh \
 && mkdir -p /var/mail/vhosts \
 && chown -R dovecot:dovecot /var/mail/vhosts

ENTRYPOINT ["/usr/local/bin/dovecot-entrypoint.sh"]
CMD ["dovecot", "-F"]
