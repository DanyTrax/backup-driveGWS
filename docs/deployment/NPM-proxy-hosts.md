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
  - **Websockets Support**: **on**
- **SSL**
  - SSL Certificate: *Request a new SSL Certificate*
  - Email: tu email
  - **Force SSL**, **HTTP/2**, **HSTS**: on
  - **Accept LE Terms**
- **Advanced** — pegá este bloque para que funcione el WebSocket (`/ws/...`) y los uploads grandes:

```nginx
client_max_body_size 200M;

location /ws/ {
    proxy_pass http://msa-backup-app:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 86400;
}
```

## 2) Proxy Host: webmail (`webmail.example.com`)

- **Details**
  - Domain names: `webmail.example.com`
  - Scheme: `http`
  - Forward Hostname / IP: `msa-backup-roundcube`
  - Forward Port: `80`
  - Cache Assets: on
  - **Block Common Exploits: off** (recomendado). Con *on*, NPM puede bloquear o alterar la URL del SSO (`?_action=plugin.msa_sso&token=<jwt>`) y Roundcube termina en el login sin token.
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
