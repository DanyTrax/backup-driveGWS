# Runbook de deployment — Dockge

Este documento describe el orden de arranque y los pasos manuales para dejar el proyecto corriendo en un VPS con Dockge ya instalado.

> Convención: asumimos `/opt/stacks/` como raíz de stacks de Dockge.

## 0) Requisitos previos en el VPS

- Docker >= 24
- Dockge instalado y accesible
- DNS de los subdominios apuntando a la IP del VPS (A records):
  - `backup.example.com` → plataforma
  - `webmail.example.com` → roundcube
- Puertos 80/443 libres en el host (si ya tienes Mailcow, confirmá que no los pisa)

## 1) Crear la red compartida (una sola vez)

```bash
docker network create proxy-net
```

Podés usar el script incluido:

```bash
bash scripts/create-proxy-net.sh
```

## 2) Subir la pila de Nginx Proxy Manager

En Dockge → **Compose** → **New Stack** → nombre: `npm-stack`.
Pegá el contenido de [npm-stack.yml](npm-stack.yml) y **Deploy**.

Primer login NPM:

- URL: `http://IP_DEL_VPS:81`
- Usuario: `admin@example.com`
- Password: `changeme`
- Cambiá el email y la contraseña inmediatamente.

## 3) Clonar el repo en el host (para bind-mount de git refresh)

```bash
mkdir -p /opt/stacks/backup-stack
cd /opt/stacks/backup-stack
git clone https://github.com/DanyTrax/backup-driveGWS.git .
```

## 4) Preparar `.env`

```bash
cp .env.example .env
bash scripts/generate-secrets.sh >> .env    # genera secretos random, revisá y limpiá duplicados
nano .env                                    # completá POSTGRES_USER, POSTGRES_DB, DOMAIN_*
```

> `DOMAIN_PLATFORM` y `DOMAIN_WEBMAIL` los podés dejar vacíos de entrada. Los vas a setear cuando corras el wizard (guía E).

## 5) Chequeo previo

```bash
bash scripts/first_run_check.sh
```

Todo debe salir en verde.

## 6) Subir la pila `backup-stack`

En Dockge → **Compose** → **New Stack** → nombre: `backup-stack`.

- Pegá [`docker/docker-compose.yml`](../../docker/docker-compose.yml) (modificá las rutas relativas si la pila vive en otro path que no sea `/opt/stacks/backup-stack/docker/`).
- **Deploy**. Esperá a que todos los servicios queden sanos.

Servicios esperados:
- `msa-backup-postgres` — healthy
- `msa-backup-redis` — healthy
- `msa-backup-app` — healthy (endpoint `GET /api/health` responde 200)
- `msa-backup-worker` — running
- `msa-backup-beat` — running
- `msa-backup-dovecot` — running
- `msa-backup-roundcube` — running

## 7) Configurar los Proxy Hosts en NPM

Ver detalle en [NPM-proxy-hosts.md](NPM-proxy-hosts.md).

Resumen:

| Host público               | Forward scheme | Forward Hostname         | Port |
| -------------------------- | -------------- | ------------------------ | ---- |
| `backup.example.com`       | `http`         | `msa-backup-app`         | 8000 |
| `webmail.example.com`      | `http`         | `msa-backup-roundcube`   | 80   |

Activá **SSL (Let's Encrypt)**, **Force SSL**, **HTTP/2** y **HSTS**.
En la plataforma, en *Advanced* agregá el bloque de WebSocket para `/ws`.

## 8) Crear el SuperAdmin inicial

Las migraciones (incluido el seed de roles y permisos) corren solas al primer arranque del contenedor `app` (ver `scripts/entrypoint.sh`). Pero el primer usuario SuperAdmin tenés que crearlo vos a mano:

```bash
docker exec -it msa-backup-app python -m scripts.bootstrap_admin -i
```

Te pide email, nombre y contraseña (mín. 12 chars). Se rehúsa a correr si ya existe un SuperAdmin, salvo que le pases `--force`.

También funciona en modo no interactivo para provisioning automatizado:

```bash
docker exec msa-backup-app python -m scripts.bootstrap_admin \
  --email admin@example.com --name "Admin" --password "LongEnoughPassword1!"
```

## 9) Primer acceso a la plataforma

1. Entrá a `https://backup.example.com` y logueate con el SuperAdmin que acabás de crear.
2. Te aparece el **wizard de first-run** con 5 guías (A-E). Seguilas en orden.
3. Al finalizar la guía E volvés al wizard, pegás `backup.example.com` y `webmail.example.com` y le das a validar. El botón **Verificar DNS/SSL** golpea los 2 hosts y confirma que la pila responde bien.

## 10) Actualizar la plataforma (Git Refresh)

Dos modos, elegí uno en `.env` → `GIT_REFRESH_MODE`:

- **webhook** (recomendado en prod): GitHub Actions empuja una imagen a GHCR, un webhook le avisa a la plataforma y hace `docker pull` + `docker compose up -d` del stack. Cero downtime visible.
- **bind_mount**: desde la UI (o con `docker exec`) corrés `scripts/refresh.sh` → `git pull` en `/app` + reinstalación de deps + alembic. Después reiniciá el stack desde Dockge.

## 11) Troubleshooting rápido

| Síntoma                                         | Chequeo                                                                          |
|-------------------------------------------------|----------------------------------------------------------------------------------|
| `backup.example.com` da 502 en NPM              | `msa-backup-app` no está en `proxy-net` o el puerto 8000 no responde.            |
| Roundcube no loguea                              | Dovecot no ve la base; revisá `docker logs msa-backup-dovecot`.                  |
| Celery no procesa jobs                          | Redis auth incorrecta; revisá `REDIS_PASSWORD` en `.env` y reinicia `worker`.    |
| WebSocket cierra en el cliente                  | En NPM → Advanced, falta `proxy_set_header Upgrade $http_upgrade`.               |
| Error `permission denied` en `/var/mail/vhosts` | El volumen `maildirs` se creó con UID distinto a 5000. Recreá volumen.           |
