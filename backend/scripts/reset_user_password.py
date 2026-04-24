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
  --connection-only  Solo imprime host/BD/usuario de Postgres de este contenedor y sale (diagnóstico).
  --show-target      Igual que arriba pero además sigue con el reset si indicás contraseña.
  --verify-password 'X'  Comprueba si X coincide con el hash guardado (no modifica nada).

Las contraseñas se normalizan un poco (quita \\r, BOM y espacios al inicio/final) para evitar fallos al pegar desde Windows.

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
from app.core.security import hash_password, verify_password
from app.models.users import SysUser

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_password(pw: str) -> str:
    """Evita fallos por pegar desde Windows (\\r), BOM o espacios accidentales al borde."""
    return pw.replace("\ufeff", "").replace("\r", "").strip()


async def _verify_only(email: str, password: str) -> None:
    email_norm = email.lower().strip()
    password = _normalize_password(password)
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(SysUser).where(SysUser.email == email_norm))
        ).scalar_one_or_none()
        if user is None:
            print(f"[verify] no existe usuario: {email_norm}", file=sys.stderr)
            sys.exit(1)
        ok = verify_password(password, user.password_hash)
        print(f"[verify] contraseña {'COINCIDE' if ok else 'NO coincide'} con la BD que ve este contenedor")
        if not ok:
            sys.exit(2)


async def _run(email: str, password: str, *, clear_mfa: bool) -> None:
    email_norm = email.lower().strip()
    password = _normalize_password(password)
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
    p.add_argument(
        "--connection-only",
        action="store_true",
        help="Solo mostrar a qué Postgres se conecta esta app y salir",
    )
    p.add_argument(
        "--show-target",
        action="store_true",
        help="Imprimir destino Postgres antes de resetear (no sale solo)",
    )
    p.add_argument(
        "--verify-password",
        metavar="PLAINTEXT",
        help="Solo probar si esta contraseña cuadra con el hash en BD (no cambia nada)",
    )
    args = p.parse_args()

    if not EMAIL_RE.match(args.email):
        sys.exit("Email inválido.")

    def _print_db_target() -> None:
        from app.core.config import get_settings

        s = get_settings()
        print(
            f"[reset_user_password] la app en este contenedor usa: "
            f"host={s.postgres_host!r} port={s.postgres_port} db={s.postgres_db!r} user={s.postgres_user!r}"
        )
        print(
            "[reset_user_password] tu psql debe apuntar al MISMO host y misma db; "
            "si no, el hash que ves no es el que usa el login."
        )

    if args.connection_only:
        _print_db_target()
        return

    if args.show_target:
        _print_db_target()

    if args.verify_password is not None:
        asyncio.run(_verify_only(args.email, args.verify_password))
        return

    if args.password:
        pw = args.password
    else:
        if not sys.stdin.isatty():
            sys.exit("Sin TTY interactivo: usá --password o ejecutá con docker exec -it ...")
        pw1 = getpass.getpass("Nueva contraseña: ")
        pw2 = getpass.getpass("Repetir: ")
        pw1, pw2 = _normalize_password(pw1), _normalize_password(pw2)
        if pw1 != pw2:
            sys.exit(
                "Las contraseñas no coinciden. "
                "Probá --password '...' entre comillas simples o revisá espacios al pegar."
            )
        pw = pw1

    pw = _normalize_password(pw)
    if len(pw) < 12:
        sys.exit("La contraseña debe tener al menos 12 caracteres.")

    asyncio.run(_run(args.email, pw, clear_mfa=args.clear_mfa))


if __name__ == "__main__":
    main()
