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
RUN chmod +x /usr/local/bin/dovecot-entrypoint.sh \
 && mkdir -p /var/mail/vhosts \
 && chown -R dovecot:dovecot /var/mail/vhosts

ENTRYPOINT ["/usr/local/bin/dovecot-entrypoint.sh"]
CMD ["dovecot", "-F"]
