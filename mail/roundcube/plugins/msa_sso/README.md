# msa_sso — Roundcube SSO plugin for MSA Backup Commander

Allows the platform to open Roundcube sessions on behalf of two actors:

- **Admin master** (SuperAdmin/Operator) browses any user's backup mailbox without knowing
  their IMAP password, by leveraging Dovecot's master-user feature.
- **Client session**, initiated by a magic link the platform sends to the client.

## Magic link (first_setup, etc.)

El enlace apunta al **API** (no a Roundcube): `https://<DOMAIN_PLATFORM>/api/webmail/magic-redeem?token=...&purpose=...`.
Ahí se valida el token, se marca como consumido y se responde **302** a  
`https://<DOMAIN_WEBMAIL>/?_action=plugin.msa_sso&token=<jwt>`.

Sin `DOMAIN_PLATFORM` en `.env`, el enlace puede construirse mal; configurá ambos dominios.

## SSO directo (admin / cliente)

```text
Platform UI ──> POST /api/webmail/accounts/:id/sso-admin (o magic-redeem arriba)
       └── issue_sso_jwt ──> redirect a
       https://webmail/?_action=plugin.msa_sso&token=<jwt>

Roundcube msa_sso: verifica JWT + Redis jti, luego authenticate (master-user o cliente).
```

## Proxy / CSP (Nginx Proxy Manager, Cloudflare)

Si la consola bloquea **scripts inline** de Roundcube, en el host **webmail** aflojá CSP o
desactivá inyecciones (p. ej. Rocket Loader). El backend de la plataforma no controla los
headers del contenedor Roundcube.

## Security assumptions

- JWT signed with platform `SECRET_KEY` (HS256).
- `jti` cached in Redis with TTL=`exp-iat` to prevent replay.
- `max_skew` = 30s to tolerate clock drift across containers.
- Webmail only reachable via NPM with HTTPS; platform never exposes `SECRET_KEY` client-side.

## Status

Phase 1: skeleton (this file). Phase 2 hardens JWT verification and adds replay protection.
