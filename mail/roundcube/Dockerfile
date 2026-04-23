# Roundcube with msa_sso dependencies (firebase/php-jwt; phpredis ya en la imagen base).
# The stock image bind-mount from the repo had no vendor/ → PHP fatal → HTTP 500.
FROM roundcube/roundcubemail:1.6.x-apache

USER root

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

# phpredis: ya viene en roundcube/roundcubemail; instalar de nuevo con PECL falla con
# "Extension 'redis' already loaded".

COPY plugins/msa_sso /var/www/html/plugins/msa_sso
WORKDIR /var/www/html/plugins/msa_sso
RUN composer install --no-dev --no-interaction --optimize-autoloader \
  && chown -R www-data:www-data /var/www/html/plugins/msa_sso

WORKDIR /var/www/html
USER www-data
