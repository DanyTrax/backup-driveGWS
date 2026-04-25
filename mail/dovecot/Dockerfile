# =====================================================================
# Dovecot interno con auth SQL (Postgres) + master user
# Solo expuesto en red Docker interna (no al host).
# =====================================================================

FROM dovecot/dovecot:2.3

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      postgresql-client gettext-base ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Quitar *antes* de COPY conf.d: el merge nunca retira 10-auth de la imagen base; si
# no, quedaría un orden de auth roto hasta que el entrypoint lo regenere.
RUN rm -f /etc/dovecot/conf.d/10-auth.conf /etc/dovecot/conf.d/auth-sql.conf

# Config files (rendered from templates at entrypoint with envsubst)
COPY conf.d/ /etc/dovecot/conf.d/
COPY templates/ /etc/dovecot/templates/
COPY entrypoint.sh /usr/local/bin/dovecot-entrypoint.sh
# Fallar el build si el contexto no trae plantillas (p. ex. .dockerignore que excluye templates/).
RUN set -eux; \
  test -s /etc/dovecot/templates/10-auth.conf.tpl; \
  test -s /etc/dovecot/templates/auth-sql.conf.tpl; \
  grep -q 'auth_master_user_separator' /etc/dovecot/templates/10-auth.conf.tpl
RUN chmod +x /usr/local/bin/dovecot-entrypoint.sh \
 && mkdir -p /var/mail/vhosts \
 && chown -R dovecot:dovecot /var/mail/vhosts

ENTRYPOINT ["/usr/local/bin/dovecot-entrypoint.sh"]
CMD ["dovecot", "-F"]
