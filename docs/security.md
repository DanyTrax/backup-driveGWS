# Seguridad — MSA Backup Commander

Resumen de controles aplicados. Extensión en Fase 2 (auditorías externas, pentesting).

## Autenticación

- Passwords hasheados con **argon2id** (passlib).
- **JWT** HS256 para API; access 15 min, refresh 7 d; rotación + revocación via `sys_sessions`.
- **MFA TOTP** opcional para SuperAdmin (configurable por feature flag).
- **Lockout exponencial**: 5 intentos fallidos → 1 min, 10 → 5 min, 15 → 30 min, 20 → 24 h (y notificación al admin).

## Autorización

- RBAC: `SuperAdmin`, `Operator`, `Auditor`.
- Matriz de permisos en `sys_permissions` con granularidad por módulo y acción (`view/edit/create/delete`).
- Verificación en middleware + en cada endpoint (doble barrera).

## Transporte

- HTTPS forzado por NPM (HSTS, HTTP/2, Let's Encrypt).
- Dovecot e IMAP **nunca** expuestos al host — tráfico siempre dentro de la bridge `internal`.
- Gmail API usada para correos salientes de la plataforma → no abrimos SMTP.

## Headers HTTP

Middleware `SecurityHeadersMiddleware`:

- `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy` estricta, sin `unsafe-inline` en scripts.
- `Permissions-Policy: geolocation=(), microphone=(), camera=()`.

## Entradas del usuario

- Pydantic v2 valida cada request body. Enums cerrados para campos críticos.
- Cualquier comando que invoque `rclone`/`gyb`/`git` pasa por `shell_safe.safe_run(binary, argv_list)` con allow-list y `shell=False`.
- Nada se concatena en un string de shell. Imposible inyección.

## Datos en reposo

- `service-account.json` y refresh tokens cifrados con **Fernet** (`FERNET_KEY`).
- Postgres bind-mount de `pg_data`; cifrado a nivel volumen recomendado (dm-crypt/LUKS en el host).
- `imap_password_hash` en argon2id — Dovecot nunca recibe la contraseña en texto plano.

## Rate limiting

- `/auth/login`: 5/min por IP.
- `/auth/magic-link`: 3/hora por cuenta de destino.
- API genérica: 60/min por token.
- Implementado con Redis + sliding window.

## Auditoría

- Tabla `sys_audit`: cada acción de usuario (login, cambio de rol, aprobación de cuenta, disparo de backup, restore, borrado, cambio de setting).
- Inmutable; solo INSERT. Retención según `LOG_RETENTION_DAYS`.

## Secretos de CI

- GitHub Actions usa secrets `GHCR_TOKEN`, nunca tokens con scope más amplio que `write:packages`.
- No se commitea nada a `main` sin revisión + lint + tests.

## Pendientes (Fase 2)

- WebAuthn / Passkeys para SuperAdmin.
- Rotación automática de `FERNET_KEY` con envelope encryption.
- SBOM (`syft`) y scanning (`trivy`) en el pipeline de imágenes.
- Integración con OpenTelemetry + Sentry para traceability.
