#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from sqlite_store import DB_PATH


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = Path(__file__).resolve().with_name("postgres_schema.sql")

TABLE_ORDER = [
    "users",
    "app_meta",
    "ai_jobs",
    "ai_job_steps",
    "access_logs",
    "ai_conversations",
    "user_sessions",
    "guilds",
    "teams",
    "team_members",
    "players",
    "matches",
    "match_players",
    "season_player_dimension_stats",
    "season_team_dimension_stats",
    "membership_requests",
]

TRUNCATE_ORDER = list(reversed(TABLE_ORDER))


def import_psycopg():
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit(
            "缺少 PostgreSQL 驱动。请先安装：python3 -m pip install 'psycopg[binary]>=3,<4'"
        ) from exc
    return psycopg


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate werewolf-stats data from SQLite to PostgreSQL.")
    parser.add_argument(
        "--sqlite-db",
        type=Path,
        default=DB_PATH,
        help="Source SQLite database path.",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="Target PostgreSQL DATABASE_URL. Defaults to environment variable DATABASE_URL.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=SCHEMA_PATH,
        help="PostgreSQL schema SQL file.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to PostgreSQL. Without this flag the script only prints source counts.",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Delete existing target rows before importing. Only valid with --apply.",
    )
    parser.add_argument(
        "--skip-schema",
        action="store_true",
        help="Do not execute the PostgreSQL schema file before importing.",
    )
    return parser.parse_args(argv)


def sqlite_connection(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise SystemExit(f"SQLite 数据库不存在：{path}")
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def table_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    if not rows:
        raise SystemExit(f"SQLite 缺少表：{table_name}")
    return [str(row["name"]) for row in rows]


def table_count(connection: Any, table_name: str, *, sqlite: bool) -> int:
    if sqlite:
        row = connection.execute(f'SELECT COUNT(*) AS count FROM "{table_name}"').fetchone()
        return int(row["count"] or 0)
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
        return int(cursor.fetchone()[0] or 0)


def source_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {table_name: table_count(connection, table_name, sqlite=True) for table_name in TABLE_ORDER}


def print_counts(title: str, counts: dict[str, int]) -> None:
    print(title)
    for table_name in TABLE_ORDER:
        print(f"- {table_name}: {counts.get(table_name, 0)}")


def execute_schema(pg_connection: Any, schema_path: Path) -> None:
    schema_sql = schema_path.read_text(encoding="utf-8")
    with pg_connection.cursor() as cursor:
        cursor.execute(schema_sql)


def truncate_target(pg_connection: Any) -> None:
    with pg_connection.cursor() as cursor:
        for table_name in TRUNCATE_ORDER:
            cursor.execute(f'TRUNCATE TABLE "{table_name}" CASCADE')


def copy_table(sqlite_connection: sqlite3.Connection, pg_connection: Any, table_name: str) -> int:
    columns = table_columns(sqlite_connection, table_name)
    column_sql = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = f'INSERT INTO "{table_name}" ({column_sql}) VALUES ({placeholders})'
    rows = sqlite_connection.execute(f'SELECT {column_sql} FROM "{table_name}"').fetchall()
    if not rows:
        return 0
    values = [tuple(row[column] for column in columns) for row in rows]
    with pg_connection.cursor() as cursor:
        cursor.executemany(insert_sql, values)
    return len(values)


def target_counts(pg_connection: Any) -> dict[str, int]:
    return {table_name: table_count(pg_connection, table_name, sqlite=False) for table_name in TABLE_ORDER}


def validate_counts(source: dict[str, int], target: dict[str, int]) -> list[str]:
    errors = []
    for table_name in TABLE_ORDER:
        if source.get(table_name, 0) != target.get(table_name, 0):
            errors.append(f"{table_name}: SQLite={source.get(table_name, 0)} PostgreSQL={target.get(table_name, 0)}")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    with sqlite_connection(args.sqlite_db) as sqlite_db:
        counts = source_counts(sqlite_db)
        print_counts("SQLite 源库行数：", counts)
        if not args.apply:
            print("\n当前为 dry-run。确认目标库后加 --apply 执行迁移。")
            return 0
        if not args.database_url:
            raise SystemExit("缺少 DATABASE_URL。请通过环境变量或 --database-url 指定 PostgreSQL 连接。")
        if args.truncate is False:
            print("\n未指定 --truncate：脚本会向目标库追加插入。若目标库已有数据，可能触发主键冲突。")

        psycopg = import_psycopg()
        with psycopg.connect(args.database_url) as pg_connection:
            with pg_connection.transaction():
                if not args.skip_schema:
                    execute_schema(pg_connection, args.schema)
                if args.truncate:
                    truncate_target(pg_connection)
                copied_counts = {}
                for table_name in TABLE_ORDER:
                    copied_counts[table_name] = copy_table(sqlite_db, pg_connection, table_name)
                print_counts("\n本次复制行数：", copied_counts)
            target = target_counts(pg_connection)
        errors = validate_counts(counts, target)
        print_counts("\nPostgreSQL 目标库行数：", target)
        if errors:
            print("\n迁移后行数不一致：", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 2
    print("\n迁移完成，行数校验通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
