"""Fijar o rectificar la contraseña IMAP (gw_accounts) desde SSH, con el MISMO hash que la API / Dovecot.

Misma lógica que "Fijar contraseña" en la plataforma (SHA512-CRYPT $6$, mismo crypt(3) que Dovecot). No uses UPDATE manual
en psql con la salida de doveadm en bash: el carácter $ en el hash se rompe con las comillas del shell.

Uso (contenedor de la app, el que tiene /app y Python):

    docker exec -it msa-backup-app python /app/scripts/set_gw_imap_password.py \\
        --email administracion@themsagroup.com

Te pedirá la contraseña dos veces (mín. 10 caracteres, igual que la API IMAP).

O (evitar dejar rastro en historial del host: preferible no pegar clave en línea; si hace falta):

    docker exec -it msa-backup-app python /app/scripts/set_gw_imap_password.py \\
        --email administracion@themsagroup.com --password 'ClaveLargaSegura10+'

Comprobar que app y Dovecot apuntan al mismo Postgres (sin email):

    docker exec msa-backup-app python /app/scripts/set_gw_imap_password.py --connection-only

Tras el script, probar IMAP (misma clave que acabas de poner):

    docker exec -it msa-backup-dovecot doveadm auth test "correo@dominio" "MismaClave"
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from sqlalchemy import select
from sqlalchemy import func

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.security import hash_imap_password, verify_imap_password
from app.models.accounts import GwAccount

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_password(pw: str) -> str:
    return pw.replace("\ufeff", "").replace("\r", "").strip()


async def _run(email: str, password: str) -> None:
    email_norm = email.lower().strip()
    try:
        pw_hash = hash_imap_password(password)
    except ValueError as e:
        print(f"[set_gw_imap_password] {e} (IMAP: mín. 10 caracteres)", file=sys.stderr)
        sys.exit(1)

    async with AsyncSessionLocal() as session:
        r = await session.execute(
            select(GwAccount).where(func.lower(GwAccount.email) == email_norm)
        )
        acc = r.scalar_one_or_none()
        if acc is None:
            print(
                f"[set_gw_imap_password] no hay gw_accounts con email: {email_norm}",
                file=sys.stderr,
            )
            sys.exit(1)

        acc.imap_password_hash = pw_hash
        acc.imap_password_set_at = datetime.now(timezone.utc)
        acc.imap_enabled = True
        acc.imap_failed_attempts = 0
        acc.imap_locked_until = None
        await session.commit()
        print(
            "[set_gw_imap_password] IMAP listo (SHA512-CRYPT, hash $6$ crudo en BD; comprobar con "
            "doveadm auth test) para: "
            f"{acc.email}"
        )


async def _verify_from_db(email: str, password: str) -> None:
    email_norm = email.lower().strip()
    async with AsyncSessionLocal() as session:
        r = await session.execute(
            select(GwAccount.imap_password_hash).where(func.lower(GwAccount.email) == email_norm)
        )
        h = r.scalar_one_or_none()
    if h is None or h == "":
        print(f"[set_gw_imap_password] no hay imap_password_hash en BD para: {email_norm}", file=sys.stderr)
        sys.exit(1)
    h = str(h).strip()
    print(f"[set_gw_imap_password] len(hash)={len(h)} prefix={h[:7]}…")
    ok = verify_imap_password(password, h)
    print(f"[set_gw_imap_password] verify_imap_password (misma lógica que la API) = {ok}")


async def _doveadm_hint_from_db(email: str) -> None:
    """Imprime un comando con el hash real (doveadm pw -t; no uses el literal 'HASH')."""
    email_norm = email.lower().strip()
    async with AsyncSessionLocal() as session:
        r = await session.execute(
            select(GwAccount.imap_password_hash).where(func.lower(GwAccount.email) == email_norm)
        )
        h = r.scalar_one_or_none()
    if h is None or str(h).strip() == "":
        print(f"[set_gw_imap_password] no hay imap_password_hash en BD para: {email_norm}", file=sys.stderr)
        sys.exit(1)
    h = str(h).strip()
    print(
        "[set_gw_imap_password] Probar el mismo string que lee el passdb SQL (doveadm pw -t acepta $6$ crudo).\n"
        "Ojo: 'HASH' o texto inventado no sirve: hubo 'Missing {scheme} prefix' por probar con la palabra HASH.\n"
    )
    # repr(h) → comillas de Python, seguro en bash si el hash no trae ' (no debería)
    print("docker exec msa-backup-dovecot doveadm pw -t \\")
    print(f"  {repr(h)} -p 'TUCLAVE'")
    print("\nO en dos líneas, sustituyendo el hash (variable evita $ en el shell):")
    print("  H=" + repr(h))
    print("  docker exec msa-backup-dovecot doveadm pw -t \"$H\" -p 'TUCLAVE'")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Fijar contraseña IMAP / webmail (gw_accounts, mismo hash que la API)."
    )
    p.add_argument(
        "--email",
        help="Email en gw_accounts (obligatorio salvo con --connection-only)",
    )
    p.add_argument(
        "--password",
        help="Nueva clave (≥10 caracteres). Si no, se pide con getpass.",
    )
    p.add_argument(
        "--connection-only",
        action="store_true",
        help="Solo mostrar a qué Postgres conecta la app (debe ser el misma pila que Dovecot)",
    )
    p.add_argument(
        "--verify-password",
        metavar="PLAINTEXT",
        help="Solo: lee hash de gw_accounts y prueba verify_imap_password (no escribe nada en BD)",
    )
    p.add_argument(
        "--doveadm-hint",
        action="store_true",
        help="Solo: imprime doveadm pw -t con el hash real de la BD (no poner literal 'HASH')",
    )
    args = p.parse_args()

    if args.connection_only:
        s = get_settings()
        print(
            f"[set_gw_imap_password] app → postgres host={s.postgres_host!r} port={s.postgres_port} "
            f"db={s.postgres_db!r} user={s.postgres_user!r}"
        )
        print(
            "[set_gw_imap_password] Debe ser la misma instancia que Dovecot (auth SQL). Compara en el VPS con:\n"
            "  docker exec msa-backup-dovecot printenv POSTGRES_HOST POSTGRES_PORT POSTGRES_DB\n"
            "  Si el host o la BD difieren, set_gw_imap_password actualiza otra base y dovecot auth falla."
        )
        return

    if not args.email:
        p.error("--email es obligatorio (excepto con --connection-only)")

    if not EMAIL_RE.match(args.email):
        sys.exit("Email inválido.")

    if args.doveadm_hint:
        asyncio.run(_doveadm_hint_from_db(args.email))
        return

    if args.verify_password is not None:
        pw = _normalize_password(args.verify_password)
        if len(pw) < 1:
            sys.exit("Contraseña vacía.")
        asyncio.run(_verify_from_db(args.email, pw))
        return

    if args.password:
        pw = _normalize_password(args.password)
    else:
        if not sys.stdin.isatty():
            sys.exit("Sin TTY: usá --password o docker exec -it ...")
        a = getpass.getpass("Nueva contraseña IMAP (≥10): ")
        b = getpass.getpass("Repetir: ")
        a, b = _normalize_password(a), _normalize_password(b)
        if a != b:
            sys.exit("Las contraseñas no coinciden.")
        pw = a

    if len(pw) < 10:
        sys.exit("IMAP: la contraseña debe tener al menos 10 caracteres (igual que en la API).")

    asyncio.run(_run(args.email, pw))


if __name__ == "__main__":
    main()
