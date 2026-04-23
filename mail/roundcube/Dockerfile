# Roundcube with msa_sso dependencies (firebase/php-jwt; phpredis ya en la imagen base).
# The stock image bind-mount from the repo had no vendor/ → PHP fatal → HTTP 500.
FROM roundcube/roundcubemail:1.6.x-apache

USER root

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

# phpredis: ya viene en roundcube/roundcubemail; instalar de nuevo con PECL falla con
# "Extension 'redis' already loaded".

# Instalar el plugin en /usr/src (fuente del entrypoint), no en /var/www/html:
# - Si solo existe plugins/msa_sso bajo /var/www/html, el arranque hace tar desde
#   /usr/src sobre un directorio parcial → errores de permiso y plugins rotos.
# - El docker-entrypoint copia /usr/src/roundcubemail → $PWD (/var/www/html); así
#   msa_sso (con vendor/) llega en la misma extracción que el core.
COPY plugins/msa_sso /usr/src/roundcubemail/plugins/msa_sso
WORKDIR /usr/src/roundcubemail/plugins/msa_sso
RUN composer install --no-dev --no-interaction --optimize-autoloader \
  && chown -R www-data:www-data /usr/src/roundcubemail/plugins/msa_sso

WORKDIR /var/www/html
# No usar USER www-data aquí: el entrypoint oficial debe ejecutarse como root para
# el tar inicial y la configuración; Apache sigue sirviendo como www-data.
