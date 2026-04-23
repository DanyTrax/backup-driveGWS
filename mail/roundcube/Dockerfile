# Roundcube with msa_sso dependencies (firebase/php-jwt + phpredis).
# The stock image bind-mount from the repo had no vendor/ → PHP fatal → HTTP 500.
FROM roundcube/roundcubemail:1.6.x-apache

USER root

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

# phpredis (msa_sso single-use JTI in Redis)
RUN apt-get update \
  && apt-get install -y --no-install-recommends $PHPIZE_DEPS \
  && pecl install redis \
  && docker-php-ext-enable redis \
  && apt-get purge -y $PHPIZE_DEPS \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/*

COPY plugins/msa_sso /var/www/html/plugins/msa_sso
WORKDIR /var/www/html/plugins/msa_sso
RUN composer install --no-dev --no-interaction --optimize-autoloader \
  && chown -R www-data:www-data /var/www/html/plugins/msa_sso

WORKDIR /var/www/html
USER www-data
