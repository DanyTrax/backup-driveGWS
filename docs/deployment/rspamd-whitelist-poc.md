# PoC: lista blanca Rspamd vía HTTP (Mailcow)

La plataforma publica mapas de texto plano en **`/security/`** (sin `/api`) para que Rspamd los descargue con `refresh` en `multimap.conf`.

## 1. Variables en `.env`

```bash
# Token obligatorio (Rspamd lo pone en la URL)
RSPAMD_WHITELIST_FEED_TOKEN=poné_un_secreto_largo_aqui

# Lista de prueba (coma o saltos de línea)
RSPAMD_WHITELIST_ENTRIES=dominio-prueba.com,@otro-dominio.com,ventas@tercero.com
```

Reiniciar solo **`app`** (no hace falta `worker` para backups):

```bash
cd /opt/stacks/backup-stack/docker
docker compose --env-file ../.env up -d app
```

## 2. Probar desde el VPS (sin Mailcow)

Sustituí `HOST`, `TOKEN` y dominio real:

```bash
curl -sS "https://HOST/security/whitelist_preview?token=TOKEN" | jq .
curl -sS "https://HOST/security/whitelist_dominios.inc?token=TOKEN"
curl -sS "https://HOST/security/whitelist_correos.inc?token=TOKEN"
curl -sS "https://HOST/security/normalize_test?q=@ejemplo.com&token=TOKEN" | jq .
```

Salida esperada de `whitelist_dominios.inc`:

```text
# whitelist domains
# generated_at: ...
dominio-prueba.com
otro-dominio.com
```

`ventas@tercero.com` debe aparecer solo en `whitelist_correos.inc`.

## 3. Probar desde el contenedor Rspamd (Mailcow)

Mismo VPS, otro contenedor:

```bash
# Nombre típico en Mailcow; ajustá con: docker ps | grep rspamd
docker exec "$(docker ps -qf name=rspamd)" wget -qO- \
  "https://HOST/security/whitelist_dominios.inc?token=TOKEN" | head -20
```

Si falla DNS/TLS, probá con la IP del host o la URL que use NPM hacia `app`.

## 4. Fragmento para `multimap.conf` (Mailcow)

Añadir en el override de Mailcow, por ejemplo  
`data/conf/rspamd/local.d/multimap.conf` o el custom que ya usás, **al final**:

```lua
# --- Plataforma MSA: whitelist remitentes (PoC HTTP) ---
PLATAFORMA_FROM_DOMAIN_WL {
  type = "from";
  filter = "email:domain";
  map = "https://TU_DOMINIO_PLATFORM/security/whitelist_dominios.inc?token=TU_RSPAMD_WHITELIST_FEED_TOKEN";
  score = -2050.0;
  description = "Whitelist dominios (panel MSA /security)";
  refresh = "5m";
  symbols_set = ["PLATAFORMA_FROM_DOMAIN_WL"];
}

PLATAFORMA_FROM_EMAIL_WL {
  type = "from";
  filter = "email";
  map = "https://TU_DOMINIO_PLATFORM/security/whitelist_correos.inc?token=TU_RSPAMD_WHITELIST_FEED_TOKEN";
  score = -2050.0;
  description = "Whitelist correos completos (panel MSA /security)";
  refresh = "5m";
  symbols_set = ["PLATAFORMA_FROM_EMAIL_WL"];
}
```

Reemplazá:

- `TU_DOMINIO_PLATFORM` → valor de `DOMAIN_PLATFORM` (sin `https://`).
- `TU_RSPAMD_WHITELIST_FEED_TOKEN` → mismo valor que `RSPAMD_WHITELIST_FEED_TOKEN` en `.env`.

Recargar Rspamd en Mailcow (según vuestra doc; suele ser reinicio del contenedor `rspamd-mailcow` o `docker compose restart rspamd-mailcow` dentro del stack Mailcow).

## 5. Prueba de correo

1. Añadí un dominio de prueba que controlés en `RSPAMD_WHITELIST_ENTRIES`.
2. Esperá hasta **5 minutos** (`refresh`) o reiniciá Rspamd.
3. Enviá un correo **desde** ese dominio hacia un buzón en Mailcow.
4. En la UI de Rspamd / cabeceras `X-Spamd-Result`, buscá símbolos `PLATAFORMA_FROM_*` y score bajo.

## 6. Seguridad (producción)

- El token en la URL es simple; en NPM podés restringir `/security/whitelist_*.inc` a la IP de salida del contenedor Mailcow.
- No commitear el token en git; solo en `.env`.
- Más adelante: CRUD en panel + BD; estos endpoints siguen generando los `.inc`.

## 7. NPM

Si el proxy solo enruta `/api` a `app`, añadí también:

- `/security` → mismo upstream que la app (puerto 8000).

O URL pública completa que Rspamd pueda resolver desde el contenedor Mailcow.
