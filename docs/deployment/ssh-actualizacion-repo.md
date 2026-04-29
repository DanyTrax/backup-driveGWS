# Actualización del repo por SSH (VPS / Dockge)

Guía corta para **traer cambios de Git**, aplicar **migraciones** y **reconstruir** lo que haga falta cuando la pila corre en Docker (como en [dockge-runbook.md](dockge-runbook.md)).

## 1) Conectar por SSH

```bash
ssh -i ~/.ssh/tu_clave usuario@IP_DEL_VPS
```

(Reemplazá usuario, IP y ruta de clave; si usás agente SSH, omití `-i`.)

## 2) Ir al directorio del proyecto

Convención del runbook: el repo está clonado en el host para los bind-mounts.

```bash
cd /opt/stacks/backup-stack   # o la ruta donde clonaste el repo
```

## 3) Traer el código

```bash
git fetch origin
git pull origin main
```

Si trabajás en otra rama, cambiá `main` por el nombre correspondiente.

## 4) Backend y migraciones

El contenedor **app** ejecuta `alembic upgrade head` al arrancar (`scripts/entrypoint.sh`). Tras un `git pull`, reiniciá el servicio API para que cargue código y migraciones nuevas:

```bash
cd docker
docker compose pull app worker beat 2>/dev/null || true
docker compose build app worker beat
docker compose up -d app worker beat
```

Si preferís **solo** correr migraciones sin esperar al reinicio (misma imagen/código ya montado):

```bash
docker compose exec app alembic upgrade head
```

Comprobación rápida:

```bash
curl -fsS http://127.0.0.1:8000/api/health
```

(Desde el host, el puerto puede no estar publicado; usá la URL interna de Dockge o `docker compose exec app curl -fsS http://localhost:8000/api/health`.)

## 5) Frontend (SPA)

El **build de React** se embebe en la imagen Docker en `/app/static` (ver `docker/Dockerfile.backend`). **Cambios en `frontend/` exigen reconstruir la imagen `app`** (y volver a levantar worker/beat si comparten tag), no alcanza con `git pull` solo.

El bloque del paso 4 (`docker compose build app worker beat`) ya incluye nuevo `npm run build` dentro del build de la imagen.

## 6) Permisos nuevos (RBAC Maildir)

Tras la migración `0006_mailbox_delegation`:

- Operador: `mailbox.view_all`, `mailbox.delegate`
- Auditor: `mailbox.view_delegated` (el visor Maildir solo en cuentas **delegadas** desde Usuarios → «Delegar buzones»)

Los usuarios que ya tenían sesión abierta pueden refrescar el navegador o volver a iniciar sesión para ver permisos y `mailbox_delegated_account_ids` en `/api/auth/me`.

## 7) Rollback de código (sin tocar BD)

```bash
git checkout main
git pull origin main   # o git reset --hard ORIG_HEAD según tu política
cd docker && docker compose build app worker beat && docker compose up -d app worker beat
```

Revertir migraciones de base de datos es un procedimiento aparte (`alembic downgrade`); coordinarlo con copia de seguridad de Postgres si aplica.
