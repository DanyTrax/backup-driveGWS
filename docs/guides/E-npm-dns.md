# Guía E — NPM + DNS

Este es el último paso del wizard. El objetivo es confirmar que los dos subdominios de la plataforma están correctamente publicados a través de tu Nginx Proxy Manager.

## Pasos

1. Comprobá tus DNS (A records):

```bash
dig +short backup.example.com
dig +short webmail.example.com
```

Ambos deben devolver la IP pública del VPS.

2. Si todavía no lo hiciste, creá los dos Proxy Hosts en NPM siguiendo [NPM-proxy-hosts.md](../deployment/NPM-proxy-hosts.md).

3. En el wizard, pegá los dos FQDN exactos (sin protocolo, sin ruta) y pulsá **Verificar**. La plataforma va a:

- Hacer un `GET https://<platform>/api/health` desde el contenedor → debe responder 200.
- Hacer un `GET https://<webmail>/` → debe responder 200 (HTML de Roundcube).
- Verificar la cabecera `Strict-Transport-Security` en ambos.
- Loguear la IP que el proxy reenvía (para confirmar que el `X-Forwarded-For` llega bien).

4. Cuando los 4 chequeos están en verde, hacé clic en **Finalizar wizard**. La plataforma:

- Guarda los dominios en `sys_settings`.
- Regenera las entradas `CSP` y `CORS` en tiempo real.
- Te lleva al dashboard principal.
