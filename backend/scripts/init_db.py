"""Create all AgentGuard database tables.

This applies every Alembic migration up to ``head`` using the connection
configured by ``DATABASE_URL`` (loaded from ``.env`` / environment variables).

Usage (from the repository root):

    python backend/scripts/init_db.py

The target database must already exist. Create it first with:

    createdb agentguard

Options:

    python backend/scripts/init_db.py --revision head
    python backend/scripts/init_db.py --sql   # print SQL instead of applying
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from alembic import command
from alembic.config import Config

from backend.app.core.config import settings


def _safe_url(url: str) -> str:
    """Return the database URL with the password masked."""
    parts = urlsplit(url)
    if parts.password is None:
        return url
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    user = parts.username or ""
    netloc = f"{user}:***@{host}{port}"
    return urlunsplit(parts._replace(netloc=netloc))


def build_alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return config


def create_tables(revision: str = "head", sql: bool = False) -> None:
    config = build_alembic_config()
    print(f"Database: {_safe_url(settings.DATABASE_URL)}")

    if sql:
        command.upgrade(config, revision, sql=True)
        return

    try:
        command.upgrade(config, revision)
    except Exception as exc:  # noqa: BLE001 - surface a helpful setup hint
        raise SystemExit(
            "Failed to create database tables.\n"
            f"  {type(exc).__name__}: {exc}\n"
            "Check that DATABASE_URL in .env is correct, PostgreSQL is running, "
            "and the target database already exists (e.g. `createdb agentguard`)."
        ) from exc

    print("Database schema is up to date.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create all AgentGuard tables by applying Alembic migrations."
    )
    parser.add_argument(
        "--revision",
        default="head",
        help="Alembic revision to upgrade to (default: head).",
    )
    parser.add_argument(
        "--sql",
        action="store_true",
        help="Emit the SQL to stdout instead of executing it.",
    )
    args = parser.parse_args()
    create_tables(revision=args.revision, sql=args.sql)


if __name__ == "__main__":
    main()
