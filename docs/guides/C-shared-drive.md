# Guía C — Shared Drive "Bóveda 38 TB"

La plataforma necesita una **Shared Drive** dedicada donde depositar los respaldos. La Service Account se convierte en *Content Manager* o *Manager* de esa Shared Drive.

## Pasos

1. Desde la cuenta admin del Workspace, entrá a <https://drive.google.com>.
2. Panel izquierdo → **Shared drives** → **New** → nombre: `MSA_Backups_Vault` (podés cambiarlo).
3. Abrí la Shared Drive → engranaje → **Manage members**.
4. Agregá como miembro el `client_email` de la Service Account (termina en `.iam.gserviceaccount.com`) con rol **Manager**.
5. (Recomendado) Agregá también al admin como Manager.
6. Copiá el **ID** de la Shared Drive (lo saca de la URL: `https://drive.google.com/drive/folders/<ID>`). Lo vas a pegar en el wizard.

## Estructura que la plataforma va a generar

```text
MSA_Backups_Vault/
└── <email_usuario>/
    ├── drive/
    │   └── YYYY_MM_DD/
    │       ├── root/
    │       └── computadoras/
    └── gmail/
        └── YYYY_MM_DD/
            └── <usuario>.mbox
```

## Cuota

Google Shared Drives tienen un hard limit de **400 000 items** (archivos + carpetas). La plataforma monitorea este contador y te dispara alertas al 70 %, 85 % y 95 %.

Si te acercás al límite:

- Activá compresión `.tar.zst` por fecha (opción en la UI).
- Agregá una segunda Shared Drive y configurá shard por usuario.
