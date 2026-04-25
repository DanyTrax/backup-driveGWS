# Nginx Proxy Manager — configuración de Proxy Hosts

Esta guía detalla, paso a paso, cómo dar de alta los dos Proxy Hosts que necesita la plataforma.

Prerrequisitos:

- NPM ya corriendo en la pila `npm-stack`.
- Red `proxy-net` creada, con `npm`, `msa-backup-app` y `msa-backup-roundcube` enganchados a ella.
- Los FQDN apuntan al VPS:
  - `backup.example.com` → A record → IP VPS
  - `webmail.example.com` → A record → IP VPS

## 1) Proxy Host: plataforma (`backup.example.com`)

- **Details**
  - Domain names: `backup.example.com`
  - Scheme: `http`
  - Forward Hostname / IP: `msa-backup-app`  ← nombre del contenedor
  - Forward Port: `8000`
  - **Cache Assets**: off
  - **Block Common Exploits**: on
  - **Websockets Support**: **on** (también para ``/api/backup/ws/progress/…``, comprobación de acceso en vivo)
- **SSL**
  - SSL Certificate: *Request a new SSL Certificate*
  - Email: tu email
  - **Force SSL**, **HTTP/2**, **HSTS**: on
  - **Accept LE Terms**
- **Advanced** — pegá este bloque para WebSockets, uploads y timeouts. **Importante:** el toggle “Websockets” de NPM no alcanza para rutas bajo `/api/`; sin el `location /api/backup/ws/` la comprobación «Cuentas → Comprobar» falla con *WebSocket cerrado*.

```nginx
client_max_body_size 200M;
# Comprobación «Cuentas → Comprobar» llama a GYB (estimate) y puede tardar varios minutos.
proxy_read_timeout 360s;
proxy_send_timeout 360s;

# Progreso en vivo (comprobación de acceso) y otros WS bajo la API
location /api/backup/ws/ {
    proxy_pass http://msa-backup-app:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 86400;
}

location /ws/ {
    proxy_pass http://msa-backup-app:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 86400;
}
```

### Probar WebSocket desde el servidor

Sustituí el host y un JWT válido (misma cookie/sesión no sirve en curl; sirve para ver si el proxy devuelve **101**):

```bash
curl -vk -o /dev/null \
  -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  "https://backup.example.com/api/backup/ws/progress/00000000-0000-0000-0000-000000000000?token=TU_JWT"
```

Si no obtenés **HTTP/1.1 101 Switching Protocols**, NPM (u otro proxy) no está pasando el upgrade en esa ruta.

## 2) Proxy Host: webmail (`webmail.example.com`)

- **Details**
  - Domain names: `webmail.example.com`
  - Scheme: `http`
  - Forward Hostname / IP: `msa-backup-roundcube`
  - Forward Port: `80`
  - Cache Assets: on
  - **Block Common Exploits: off** (sigue recomendable). Un fallo raro era WAF/URL demasiado larga con el JWT: el backend ahora emite un handoff **corto** (`…?_task=login&_action=plugin.msa_sso&rid=…` con el JWT en Redis). Si aun así el SSO abre el login vacío, desactivá *Block Common Exploits* y comprobá que el host de webmail en `.env` (`DOMAIN_WEBMAIL`) coincide con el FQDN del proxy.
  - Websockets Support: off (Roundcube no lo necesita)
- **SSL**
  - Request new SSL cert, Force SSL, HTTP/2, HSTS on
- **Advanced** — subimos el límite para adjuntos al descargar carpetas:

```nginx
client_max_body_size 200M;
proxy_buffering off;
```

## 3) Verificar

```bash
curl -I https://backup.example.com/api/health
curl -I https://webmail.example.com/
```

Ambos deben devolver 200 OK con `Strict-Transport-Security` presente.

## 4) Cerrar el puerto 81 (UI de NPM) cuando termines

Una vez configurado todo, cerrá el puerto 81 con `ufw`/`firewalld` en el host para evitar exponer el panel de NPM a Internet. Mantenelo accesible solo vía Wireguard/SSH tunneling cuando quieras modificar.
