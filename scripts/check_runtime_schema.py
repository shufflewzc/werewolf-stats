#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from typing import Any

from db_runtime import connect_runtime_db, runtime_database_summary
from schema_version import REQUIRED_SCHEMA_VERSION, SCHEMA_VERSION_META_KEY


REQUIRED_RUNTIME_TABLES = [
    "users",
    "user_scope_grants",
    "app_meta",
    "audit_logs",
    "access_logs",
    "user_sessions",
    "guilds",
    "teams",
    "players",
    "matches",
    "match_players",
]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check runtime database schema before starting the web service.")
    parser.add_argument("--database-url", default="", help="Override DATABASE_URL for this check.")
    return parser.parse_args(argv)


def row_value(row: Any, key: str, index: int = 0) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def parse_schema_version(value: Any) -> int:
    try:
        return int(str(value or "0").strip() or "0")
    except ValueError:
        return 0


def table_exists(connection: Any, table_name: str) -> bool:
    backend = getattr(connection, "backend", "")
    if backend == "postgres":
        row = connection.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = ?
            ) AS exists
            """,
            (table_name,),
        ).fetchone()
        return bool(row_value(row, "exists"))
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    summary = runtime_database_summary(args.database_url or None)
    print("运行时数据库结构检查：")
    print(f"- backend: {summary['backend']}")
    print(f"- database: {summary['database']}")
    errors: list[str] = []
    try:
        with connect_runtime_db(args.database_url or None) as connection:
            missing_tables = [
                table_name
                for table_name in REQUIRED_RUNTIME_TABLES
                if not table_exists(connection, table_name)
            ]
            if missing_tables:
                errors.append("缺少表：" + ", ".join(missing_tables))
            initialized_row = connection.execute(
                "SELECT meta_value FROM app_meta WHERE meta_key = ?",
                ("initialized",),
            ).fetchone()
            initialized = row_value(initialized_row, "meta_value")
            if initialized != "1":
                errors.append("app_meta.initialized 不是 1")
            schema_row = connection.execute(
                "SELECT meta_value FROM app_meta WHERE meta_key = ?",
                (SCHEMA_VERSION_META_KEY,),
            ).fetchone()
            schema_version = parse_schema_version(row_value(schema_row, "meta_value"))
            if schema_version < REQUIRED_SCHEMA_VERSION:
                errors.append(
                    f"schema_version={schema_version}，需要 {REQUIRED_SCHEMA_VERSION}；请先执行 scripts/apply_postgres_schema.py"
                )
    except Exception as exc:
        errors.append(f"数据库结构检查失败：{exc}")
    if errors:
        print("检查未通过：", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"检查通过。schema_version >= {REQUIRED_SCHEMA_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
