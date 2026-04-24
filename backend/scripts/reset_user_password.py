"""Restablecer contraseña de un usuario de la plataforma (admin) sin entrar por la web.

Uso típico cuando olvidaste la clave pero tenés acceso al servidor / Docker:

    docker exec -it msa-backup-app python /app/scripts/reset_user_password.py \\
        --email admin@tudominio.com

Te pedirá la nueva contraseña dos veces (no se muestra en pantalla).

O sin prompt (evitar que quede en el historial del host si podés):

    docker exec -it msa-backup-app python /app/scripts/reset_user_password.py \\
        --email admin@tudominio.com --password 'NuevaClaveSegura123!'

Opciones:
  --clear-mfa   Desactiva MFA y borra el secreto (por si no podés completar el segundo factor).

No sustituye un flujo "olvidé mi contraseña" por correo: eso requiere SMTP y tokens en la app.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import re
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.users import SysUser

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def _run(email: str, password: str, *, clear_mfa: bool) -> None:
    email_norm = email.lower().strip()
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(SysUser).where(SysUser.email == email_norm))
        ).scalar_one_or_none()
        if user is None:
            print(f"[reset_user_password] no existe usuario con email: {email_norm}", file=sys.stderr)
            sys.exit(1)

        user.password_hash = hash_password(password)
        user.failed_login_count = 0
        user.locked_until = None
        user.must_change_password = False

        if clear_mfa:
            user.mfa_enabled = False
            user.mfa_secret_encrypted = None
            user.mfa_backup_codes_encrypted = None
            user.mfa_enrolled_at = None

        await session.commit()
        print(f"[reset_user_password] contraseña actualizada para {email_norm}")
        if clear_mfa:
            print("[reset_user_password] MFA desactivado para esa cuenta.")


def main() -> None:
    p = argparse.ArgumentParser(description="Restablecer contraseña de usuario plataforma (SSH/recovery).")
    p.add_argument("--email", required=True, help="Email del usuario en sys_users")
    p.add_argument("--password", help="Nueva contraseña (opcional; si no, getpass en consola)")
    p.add_argument(
        "--clear-mfa",
        action="store_true",
        help="Quitar MFA de ese usuario (útil si perdés el segundo factor)",
    )
    args = p.parse_args()

    if not EMAIL_RE.match(args.email):
        sys.exit("Email inválido.")

    if args.password:
        pw = args.password
    else:
        if not sys.stdin.isatty():
            sys.exit("Sin TTY interactivo: usá --password o ejecutá con docker exec -it ...")
        pw1 = getpass.getpass("Nueva contraseña: ")
        pw2 = getpass.getpass("Repetir: ")
        if pw1 != pw2:
            sys.exit("Las contraseñas no coinciden.")
        pw = pw1

    if len(pw) < 12:
        sys.exit("La contraseña debe tener al menos 12 caracteres.")

    asyncio.run(_run(args.email, pw, clear_mfa=args.clear_mfa))


if __name__ == "__main__":
    main()
