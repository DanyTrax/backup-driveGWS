"""Interactive creation of the first SuperAdmin user.

Usage (inside the app container):

    docker exec -it msa-backup-app python -m scripts.bootstrap_admin

Asks for email, full name and password. Hashes with argon2id and writes into
sys_users with the SuperAdmin role. Refuses to run if at least one SuperAdmin
already exists, unless --force is passed.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import re
import sys
import uuid

from passlib.hash import argon2
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.enums import UserRole

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def _count_superadmins(session: AsyncSession) -> int:
    result = await session.execute(
        text("SELECT COUNT(*) FROM sys_users WHERE role_code = 'super_admin'")
    )
    return int(result.scalar() or 0)


async def _role_id_for(session: AsyncSession, role_code: str) -> uuid.UUID:
    result = await session.execute(
        text("SELECT id FROM sys_roles WHERE code = :code"), {"code": role_code}
    )
    row = result.fetchone()
    if not row:
        raise RuntimeError(
            f"Role '{role_code}' not found. Did you run 'alembic upgrade head' first?"
        )
    return row[0]


async def _create_admin(email: str, full_name: str, password: str, force: bool) -> None:
    async with AsyncSessionLocal() as session:
        existing = await _count_superadmins(session)
        if existing and not force:
            print(
                f"[bootstrap_admin] refusing: {existing} SuperAdmin(s) already exist. "
                "Pass --force to create another one."
            )
            sys.exit(2)

        role_id = await _role_id_for(session, UserRole.SUPER_ADMIN.value)
        user_id = uuid.uuid4()
        pwd_hash = argon2.using(rounds=3, memory_cost=65536, parallelism=4).hash(password)

        await session.execute(
            text(
                """
                INSERT INTO sys_users
                  (id, email, full_name, password_hash, role_id, role_code,
                   status, must_change_password, password_changed_at)
                VALUES
                  (:id, :email, :full_name, :pw, :role_id, :role_code,
                   'active', FALSE, NOW())
                """
            ),
            {
                "id": str(user_id),
                "email": email.lower().strip(),
                "full_name": full_name.strip(),
                "pw": pwd_hash,
                "role_id": role_id,
                "role_code": UserRole.SUPER_ADMIN.value,
            },
        )
        await session.commit()
        print(f"[bootstrap_admin] SuperAdmin created: {email} (id={user_id})")


def _prompt(interactive: bool) -> tuple[str, str, str]:
    if not interactive:
        raise SystemExit("Missing flags; run with -i for interactive mode or pass --email/--name/--password.")
    email = input("Email: ").strip()
    if not EMAIL_RE.match(email):
        raise SystemExit("Invalid email.")
    full_name = input("Nombre completo: ").strip() or email.split("@")[0]
    pwd1 = getpass.getpass("Password: ")
    pwd2 = getpass.getpass("Password (confirm): ")
    if pwd1 != pwd2:
        raise SystemExit("Passwords do not match.")
    if len(pwd1) < 12:
        raise SystemExit("Password must be at least 12 characters.")
    return email, full_name, pwd1


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the initial SuperAdmin user.")
    parser.add_argument("--email")
    parser.add_argument("--name")
    parser.add_argument("--password")
    parser.add_argument("--force", action="store_true", help="Allow creating extra SuperAdmins.")
    parser.add_argument("-i", "--interactive", action="store_true")
    args = parser.parse_args()

    if args.email and args.name and args.password:
        if not EMAIL_RE.match(args.email):
            sys.exit("Invalid email.")
        email, name, pw = args.email, args.name, args.password
    else:
        email, name, pw = _prompt(interactive=True)

    asyncio.run(_create_admin(email, name, pw, force=args.force))


if __name__ == "__main__":
    main()
