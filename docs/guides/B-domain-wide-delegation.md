# Guía B — Domain-Wide Delegation (DWD)

Autorizá la Service Account creada en la guía A para que pueda actuar en nombre de cualquier usuario del Workspace.

## Pasos

1. Entrá a <https://admin.google.com/> con una cuenta de superadmin del Workspace.
2. **Security** → **Access and data control** → **API controls** → **Manage Domain Wide Delegation**.
3. **Add new**:
   - Client ID: pegá el **Unique ID** (Client ID numérico) de la Service Account.
   - OAuth scopes:

```text
https://www.googleapis.com/auth/admin.directory.user.readonly,
https://www.googleapis.com/auth/drive,
https://www.googleapis.com/auth/gmail.modify,
https://www.googleapis.com/auth/gmail.readonly,
https://www.googleapis.com/auth/gmail.send
```

4. **Authorize**.

## Impersonación del admin

La plataforma necesita un **admin impersonation email** — típicamente el mismo superadmin que creó la SA. Es el email que va en el wizard campo *Admin Google Workspace*. La plataforma usa DWD para impersonar a ese usuario cuando llama a la Admin SDK Directory API (listar cuentas).

## Validación

En el wizard hacés clic en **Probar DWD**. La plataforma:

1. Solicita un token OAuth impersonando al admin.
2. Llama `users.list()` de Admin SDK y te muestra las N cuentas del dominio.
3. Intenta leer metadata de Drive de 1 cuenta de muestra.
4. Intenta listar 1 mensaje de Gmail de esa cuenta.

Si alguno falla, te señala qué scope o paso falta.
