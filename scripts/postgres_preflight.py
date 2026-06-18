#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from db_runtime import database_backend
from schema_version import REQUIRED_SCHEMA_VERSION, SCHEMA_VERSION_META_KEY
from sqlite_store import DB_PATH


REQUIRED_TABLES = [
    "users",
    "app_meta",
    "audit_logs",
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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preflight checks before PostgreSQL runtime validation/cutover.")
    parser.add_argument(
        "--sqlite-db",
        type=Path,
        default=DB_PATH,
        help="Source SQLite database path.",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="PostgreSQL DATABASE_URL. Defaults to environment variable DATABASE_URL.",
    )
    parser.add_argument(
        "--require-wechat",
        action="store_true",
        help="Require WECHAT_MINIPROGRAM_APPID and WECHAT_MINIPROGRAM_SECRET to be configured.",
    )
    return parser.parse_args(argv)


def ok(message: str) -> None:
    print(f"[OK] {message}")


def fail(errors: list[str], message: str) -> None:
    errors.append(message)
    print(f"[FAIL] {message}")


def warn(message: str) -> None:
    print(f"[WARN] {message}")


def sqlite_table_count(connection: sqlite3.Connection, table_name: str) -> int:
    row = connection.execute(f'SELECT COUNT(*) AS count FROM "{table_name}"').fetchone()
    return int(row["count"] or 0)


def parse_schema_version(value: Any) -> int:
    try:
        return int(str(value or "0").strip() or "0")
    except ValueError:
        return 0


def check_sqlite_source(sqlite_db: Path, errors: list[str]) -> None:
    if not sqlite_db.exists():
        fail(errors, f"SQLite 源库不存在：{sqlite_db}")
        return
    with sqlite3.connect(sqlite_db) as connection:
        connection.row_factory = sqlite3.Row
        quick_row = connection.execute("PRAGMA quick_check").fetchone()
        quick_check = str(quick_row[0] if quick_row else "")
        if quick_check == "ok":
            ok("SQLite quick_check 通过。")
        else:
            fail(errors, f"SQLite quick_check 异常：{quick_check}")
        initialized_row = connection.execute(
            "SELECT meta_value FROM app_meta WHERE meta_key = 'initialized'"
        ).fetchone()
        if initialized_row and initialized_row["meta_value"] == "1":
            ok("SQLite 源库已初始化。")
        else:
            fail(errors, "SQLite 源库 app_meta.initialized 不是 1。")
        users = sqlite_table_count(connection, "users")
        matches = sqlite_table_count(connection, "matches")
        ok(f"SQLite 源库行数：users={users}, matches={matches}。")


def import_psycopg(errors: list[str]) -> Any | None:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        fail(errors, "缺少 psycopg。请安装 requirements.txt 或执行 python3 -m pip install 'psycopg[binary]>=3,<4'。")
        return None
    ok("psycopg 已安装。")
    return psycopg, dict_row


def check_postgres(database_url: str, errors: list[str]) -> None:
    if database_backend(database_url) != "postgres":
        fail(errors, "DATABASE_URL 不是 PostgreSQL 连接串。")
        return
    imported = import_psycopg(errors)
    if not imported:
        return
    psycopg, dict_row = imported
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            row = connection.execute("SELECT 1 AS ok").fetchone()
            if int(row["ok"]) == 1:
                ok("PostgreSQL 可连接。")
            missing_tables = []
            for table_name in REQUIRED_TABLES:
                exists_row = connection.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = %s
                    ) AS exists
                    """,
                    (table_name,),
                ).fetchone()
                if not exists_row["exists"]:
                    missing_tables.append(table_name)
            if missing_tables:
                fail(errors, "PostgreSQL 缺少表：" + ", ".join(missing_tables))
                return
            ok("PostgreSQL 核心表存在。")
            initialized_row = connection.execute(
                "SELECT meta_value FROM app_meta WHERE meta_key = %s",
                ("initialized",),
            ).fetchone()
            if initialized_row and initialized_row["meta_value"] == "1":
                ok("PostgreSQL app_meta.initialized 为 1。")
            else:
                fail(errors, "PostgreSQL app_meta.initialized 不是 1，请先迁移数据。")
            schema_version_row = connection.execute(
                "SELECT meta_value FROM app_meta WHERE meta_key = %s",
                (SCHEMA_VERSION_META_KEY,),
            ).fetchone()
            schema_version = parse_schema_version(
                schema_version_row["meta_value"] if schema_version_row else "0"
            )
            if schema_version >= REQUIRED_SCHEMA_VERSION:
                ok(f"PostgreSQL schema_version={schema_version}。")
            else:
                fail(
                    errors,
                    f"PostgreSQL schema_version={schema_version}，需要 {REQUIRED_SCHEMA_VERSION}。请先执行 scripts/apply_postgres_schema.py。",
                )
            counts = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM users) AS users,
                    (SELECT COUNT(*) FROM matches) AS matches
                """
            ).fetchone()
            ok(f"PostgreSQL 行数：users={int(counts['users'])}, matches={int(counts['matches'])}。")
    except Exception as exc:
        fail(errors, f"PostgreSQL 连接或检查失败：{exc}")


def check_environment(args: argparse.Namespace, errors: list[str]) -> None:
    if args.require_wechat:
        for name in ["WECHAT_MINIPROGRAM_APPID", "WECHAT_MINIPROGRAM_SECRET"]:
            if os.getenv(name, "").strip():
                ok(f"{name} 已配置。")
            else:
                fail(errors, f"{name} 未配置。")
    if os.getenv("ALLOW_WECHAT_DEV_LOGIN", "").strip() == "1":
        warn("ALLOW_WECHAT_DEV_LOGIN=1 只适合本地调试，生产环境请关闭。")
    if os.getenv("COOKIE_SECURE", "").strip() in {"", "1"}:
        ok("COOKIE_SECURE 配置适合 HTTPS。")
    else:
        warn("COOKIE_SECURE 不是 1；仅建议本地 HTTP 调试使用。")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    errors: list[str] = []
    print("PostgreSQL 切换预检")
    check_environment(args, errors)
    check_sqlite_source(args.sqlite_db, errors)
    check_postgres(args.database_url, errors)
    if errors:
        print("\n预检未通过：")
        for error in errors:
            print(f"- {error}")
        return 1
    print("\n预检通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
