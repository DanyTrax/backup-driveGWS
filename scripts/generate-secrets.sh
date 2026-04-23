#!/usr/bin/env bash
# Generates strong random values for .env on first install.
# Prints KEY=value lines; redirect to a file and review before committing to .env.
set -euo pipefail

gen_urlsafe() { python3 -c "import secrets;print(secrets.token_urlsafe($1))"; }
gen_hex()     { python3 -c "import secrets;print(secrets.token_hex($1))"; }
gen_fernet()  { python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"; }

echo "# Generated on $(date -u +%FT%TZ) — review and paste into .env"
echo "SECRET_KEY=$(gen_urlsafe 48)"
echo "FERNET_KEY=$(gen_fernet)"
echo "POSTGRES_PASSWORD=$(gen_urlsafe 24)"
echo "REDIS_PASSWORD=$(gen_urlsafe 24)"
echo "DOVECOT_MASTER_PASSWORD=$(gen_urlsafe 32)"
echo "ROUNDCUBE_DES_KEY=$(gen_hex 12)"
