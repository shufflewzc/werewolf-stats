#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys

from db_runtime import connect_runtime_db, runtime_database_summary


CORE_TABLES = [
    "users",
    "guilds",
    "teams",
    "players",
    "matches",
    "match_players",
    "app_meta",
]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test the configured runtime database.")
    parser.add_argument("--database-url", default="", help="Override DATABASE_URL for this smoke test.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    summary = runtime_database_summary(args.database_url or None)
    print("运行时数据库：")
    print(f"- backend: {summary['backend']}")
    print(f"- database: {summary['database']}")
    try:
        with connect_runtime_db(args.database_url or None) as connection:
            counts = {}
            for table_name in CORE_TABLES:
                row = connection.execute(f'SELECT COUNT(*) AS count FROM "{table_name}"').fetchone()
                counts[table_name] = int(row["count"] if isinstance(row, dict) else row["count"])
            initialized_row = connection.execute(
                "SELECT meta_value FROM app_meta WHERE meta_key = ?",
                ("initialized",),
            ).fetchone()
    except Exception as exc:
        print(f"烟测失败：{exc}", file=sys.stderr)
        return 1

    print("核心表行数：")
    for table_name in CORE_TABLES:
        print(f"- {table_name}: {counts[table_name]}")
    initialized = ""
    if initialized_row:
        initialized = initialized_row["meta_value"] if isinstance(initialized_row, dict) else initialized_row["meta_value"]
    if initialized != "1":
        print("烟测失败：app_meta.initialized 不是 1。", file=sys.stderr)
        return 2
    print("烟测通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
