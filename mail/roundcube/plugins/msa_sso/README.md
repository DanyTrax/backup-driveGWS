# msa_sso — Roundcube SSO plugin for MSA Backup Commander

Allows the platform to open Roundcube sessions on behalf of two actors:

- **Admin master** (SuperAdmin/Operator) browses any user's backup mailbox without knowing
  their IMAP password, by leveraging Dovecot's master-user feature.
- **Client session**, initiated by a magic link the platform sends to the client.

## Expected flow

```text
Platform UI (React) ──> POST /api/webmail/sso  ─┐
                                                ▼
                               Backend signs JWT (HS256, exp=120s, jti=uuid)
                                                │
                               303 Redirect to  │
                               https://webmail.example.com/?_sso=<jwt>
                                                │
Roundcube (msa_sso plugin) ─── verifies JWT ──┐
                                              ▼
                            Fills login form + calls authenticate hook
                            Admin mode uses "user*master" + master password
                            Client mode uses short-lived encoded password
```

## Security assumptions

- JWT signed with platform `SECRET_KEY` (HS256).
- `jti` cached in Redis with TTL=`exp-iat` to prevent replay.
- `max_skew` = 30s to tolerate clock drift across containers.
- Webmail only reachable via NPM with HTTPS; platform never exposes `SECRET_KEY` client-side.

## Status

Phase 1: skeleton (this file). Phase 2 hardens JWT verification and adds replay protection.
