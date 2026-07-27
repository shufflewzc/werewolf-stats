#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import sys
import re
from datetime import datetime, timezone
from pathlib import Path

from schema_version import REQUIRED_SCHEMA_VERSION, SCHEMA_VERSION_META_KEY


SCHEMA_PATH = Path(__file__).resolve().with_name("postgres_schema.sql")
MIGRATIONS_DIR = Path(__file__).resolve().with_name("migrations")
MIGRATION_NAME_PATTERN = re.compile(r"^(?P<version>\d{3})_(?P<name>.+)\.sql$")


def import_psycopg():
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit(
            "缺少 PostgreSQL 驱动。请先安装：python3 -m pip install 'psycopg[binary]>=3,<4'"
        ) from exc
    return psycopg


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply PostgreSQL schema updates without copying data.")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="PostgreSQL DATABASE_URL. Defaults to environment variable DATABASE_URL.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=SCHEMA_PATH,
        help="PostgreSQL schema SQL file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if not args.database_url:
        raise SystemExit("缺少 DATABASE_URL。请通过环境变量或 --database-url 指定 PostgreSQL 连接。")
    schema_sql = args.schema.read_text(encoding="utf-8")
    psycopg = import_psycopg()
    with psycopg.connect(args.database_url) as connection:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(schema_sql)
        applied_migrations: list[str] = []
        migration_paths = sorted(MIGRATIONS_DIR.glob("*.sql")) if MIGRATIONS_DIR.is_dir() else []
        for migration_path in migration_paths:
            matched = MIGRATION_NAME_PATTERN.match(migration_path.name)
            if not matched:
                continue
            version = int(matched.group("version"))
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = %s",
                    (version,),
                )
                if cursor.fetchone():
                    continue
            migration_sql = migration_path.read_text(encoding="utf-8")
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(migration_sql)
                    cursor.execute(
                        """
                        INSERT INTO schema_migrations(version, name, applied_at)
                        VALUES (%s, %s, %s)
                        """,
                        (
                            version,
                            matched.group("name"),
                            datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        ),
                    )
            applied_migrations.append(migration_path.name)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT meta_value FROM app_meta WHERE meta_key = %s",
                (SCHEMA_VERSION_META_KEY,),
            )
            row = cursor.fetchone()
    current_version = int(row[0] or 0) if row else 0
    if current_version < REQUIRED_SCHEMA_VERSION:
        raise SystemExit(
            f"PostgreSQL 表结构版本不足：当前 {current_version}，需要 {REQUIRED_SCHEMA_VERSION}。"
        )
    print(
        f"PostgreSQL 表结构已更新。schema_version={current_version}；"
        f"new_migrations={','.join(applied_migrations) or 'none'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
