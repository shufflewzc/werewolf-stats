#!/usr/bin/env python3

from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_runtime_schema
import runtime_db_smoke
from backup_sqlite import BACKUP_DIR, archive_assets, backup_database, prune_backups
from db_runtime import connect_runtime_db, database_backend, database_url, runtime_database_summary
from schema_version import REQUIRED_SCHEMA_VERSION, SCHEMA_VERSION_META_KEY
from sqlite_store import DB_PATH


CHINA_TZ = ZoneInfo("Asia/Shanghai")
CHECK_TABLES = [
    "users",
    "app_meta",
    "ai_jobs",
    "ai_job_steps",
    "access_logs",
    "audit_logs",
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
SAFE_RESTORE_DATABASE_KEYWORDS = ("restore", "restored", "test", "staging", "sandbox", "scratch", "rehearsal")


class BackupCheckError(RuntimeError):
    pass


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a backup and verify that it can be inspected or restored.")
    parser.add_argument("--database-url", default="", help="Runtime PostgreSQL DATABASE_URL. If omitted, uses env DATABASE_URL.")
    parser.add_argument(
        "--restore-test-database-url",
        default="",
        help="Optional empty PostgreSQL database URL used for a real restore rehearsal.",
    )
    parser.add_argument("--output-dir", type=Path, default=BACKUP_DIR, help="Backup output directory.")
    parser.add_argument("--keep", type=int, default=14, help="Number of recent backups to keep.")
    parser.add_argument("--no-assets", action="store_true", help="Skip uploaded asset archive.")
    parser.add_argument(
        "--allow-unsafe-restore-target",
        action="store_true",
        help="Allow restore rehearsal into a database name that does not look like a test database.",
    )
    return parser.parse_args(argv)


def timestamp_label() -> str:
    return datetime.now(CHINA_TZ).strftime("%Y%m%d-%H%M%S")


def row_value(row, key: str, index: int = 0):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (IndexError, TypeError):
        return row[index]


def parse_schema_version(value) -> int:
    try:
        return int(str(value or "0").strip() or "0")
    except ValueError:
        return 0


def postgres_database_identity(url: str) -> tuple[str, str, str, int | None, str]:
    parsed = urlparse(url)
    database_name = unquote((parsed.path or "").lstrip("/"))
    return (
        parsed.scheme.lower(),
        unquote(parsed.username or ""),
        (parsed.hostname or "").lower(),
        parsed.port,
        database_name,
    )


def assert_safe_restore_target(source_url: str, restore_test_url: str, *, allow_unsafe: bool) -> None:
    source_identity = postgres_database_identity(source_url)
    restore_identity = postgres_database_identity(restore_test_url)
    if source_identity == restore_identity:
        raise BackupCheckError("恢复测试库连接串不能和正式库 DATABASE_URL 相同。")
    restore_database = restore_identity[-1].lower()
    if not restore_database:
        raise BackupCheckError("恢复测试库连接串缺少数据库名。")
    if allow_unsafe:
        return
    if not any(keyword in restore_database for keyword in SAFE_RESTORE_DATABASE_KEYWORDS):
        raise BackupCheckError(
            "恢复测试库名称需要包含 restore/test/staging/sandbox/scratch/rehearsal 等安全标识；"
            "确认无误后可加 --allow-unsafe-restore-target。"
        )


def sqlite_table_counts(db_path: Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        quick_row = connection.execute("PRAGMA quick_check").fetchone()
        quick_check = str(quick_row[0] if quick_row else "")
        if quick_check != "ok":
            raise BackupCheckError(f"SQLite quick_check 异常：{quick_check}")
        counts: dict[str, int] = {}
        for table_name in CHECK_TABLES:
            row = connection.execute(f'SELECT COUNT(*) AS count FROM "{table_name}"').fetchone()
            counts[table_name] = int(row["count"] or 0)
        initialized_row = connection.execute(
            "SELECT meta_value FROM app_meta WHERE meta_key = ?",
            ("initialized",),
        ).fetchone()
        if row_value(initialized_row, "meta_value") != "1":
            raise BackupCheckError("备份库 app_meta.initialized 不是 1")
        schema_row = connection.execute(
            "SELECT meta_value FROM app_meta WHERE meta_key = ?",
            (SCHEMA_VERSION_META_KEY,),
        ).fetchone()
        schema_version = parse_schema_version(row_value(schema_row, "meta_value"))
        if schema_version < REQUIRED_SCHEMA_VERSION:
            raise BackupCheckError(f"备份库 schema_version={schema_version}，需要 {REQUIRED_SCHEMA_VERSION}")
    return counts


def runtime_table_counts(url: str = "") -> dict[str, int]:
    with connect_runtime_db(url or None) as connection:
        counts: dict[str, int] = {}
        for table_name in CHECK_TABLES:
            row = connection.execute(f'SELECT COUNT(*) AS count FROM "{table_name}"').fetchone()
            counts[table_name] = int(row_value(row, "count"))
    return counts


def assert_counts_match(source_counts: dict[str, int], restored_counts: dict[str, int]) -> None:
    mismatches = [
        f"{table_name}: source={source_counts.get(table_name)} restored={restored_counts.get(table_name)}"
        for table_name in CHECK_TABLES
        if int(source_counts.get(table_name, -1)) != int(restored_counts.get(table_name, -2))
    ]
    if mismatches:
        raise BackupCheckError("备份恢复行数不一致：" + "；".join(mismatches))


def verify_asset_archive(archive_path: Path) -> int:
    if not archive_path.exists():
        return 0
    with tarfile.open(archive_path, "r:gz") as archive:
        unsafe_names = [
            member.name
            for member in archive.getmembers()
            if member.name.startswith("/") or ".." in Path(member.name).parts
        ]
        if unsafe_names:
            raise BackupCheckError("上传资源备份包含不安全路径：" + ", ".join(unsafe_names[:5]))
        return len(archive.getmembers())


def check_sqlite_backup(output_dir: Path, keep: int, no_assets: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    label = timestamp_label()
    db_backup_path = output_dir / f"werewolf_stats-{label}.db"
    asset_backup_path = output_dir / f"assets-{label}.tar.gz"
    source_counts = runtime_table_counts("")
    backup_database(db_backup_path)
    archived_assets = False if no_assets else archive_assets(asset_backup_path)
    restored_counts = sqlite_table_counts(db_backup_path)
    assert_counts_match(source_counts, restored_counts)
    asset_count = verify_asset_archive(asset_backup_path) if archived_assets else 0
    prune_backups(output_dir, keep)
    print("SQLite 备份恢复验证通过：")
    print(f"- 原数据库：{DB_PATH}")
    print(f"- 备份文件：{db_backup_path}")
    print(f"- 校验表数量：{len(CHECK_TABLES)}")
    print(f"- 校验表总行数：{sum(restored_counts.values())}")
    if archived_assets:
        print(f"- 上传资源包：{asset_backup_path}，条目 {asset_count}")
    elif not no_assets:
        print("- 上传资源包：未发现 uploads 目录，已跳过")


def require_command(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise BackupCheckError(f"缺少命令：{name}。请在服务器安装 PostgreSQL client 工具。")
    return path


def run_command(command: list[str], *, label: str) -> None:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise BackupCheckError(f"{label} 失败：{detail}")


def prune_postgres_backups(output_dir: Path, keep: int) -> None:
    if keep <= 0 or not output_dir.exists():
        return
    backups = sorted(output_dir.glob("postgres-*.dump"), key=lambda item: item.name, reverse=True)
    asset_backups = sorted(output_dir.glob("assets-*.tar.gz"), key=lambda item: item.name, reverse=True)
    for stale_path in backups[keep:] + asset_backups[keep:]:
        stale_path.unlink(missing_ok=True)


def check_postgres_backup(
    source_url: str,
    restore_test_url: str,
    output_dir: Path,
    keep: int,
    *,
    allow_unsafe_restore_target: bool = False,
    no_assets: bool = False,
) -> None:
    pg_dump = require_command("pg_dump")
    pg_restore = require_command("pg_restore")
    output_dir.mkdir(parents=True, exist_ok=True)
    label = timestamp_label()
    backup_path = output_dir / f"postgres-{label}.dump"
    asset_backup_path = output_dir / f"assets-{label}.tar.gz"
    source_counts = runtime_table_counts(source_url)
    run_command(
        [pg_dump, "--format=custom", "--no-owner", "--no-acl", "--file", str(backup_path), source_url],
        label="PostgreSQL 备份",
    )
    run_command([pg_restore, "--list", str(backup_path)], label="PostgreSQL 备份读取")
    archived_assets = False if no_assets else archive_assets(asset_backup_path)
    asset_count = verify_asset_archive(asset_backup_path) if archived_assets else 0
    if restore_test_url:
        assert_safe_restore_target(
            source_url,
            restore_test_url,
            allow_unsafe=allow_unsafe_restore_target,
        )
        run_command(
            [
                pg_restore,
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-acl",
                "--dbname",
                restore_test_url,
                str(backup_path),
            ],
            label="PostgreSQL 恢复演练",
        )
        schema_code = check_runtime_schema.main(["--database-url", restore_test_url])
        smoke_code = runtime_db_smoke.main(["--database-url", restore_test_url])
        if schema_code != 0 or smoke_code != 0:
            raise BackupCheckError("恢复后的 PostgreSQL 库未通过结构检查或 smoke")
        restored_counts = runtime_table_counts(restore_test_url)
        assert_counts_match(source_counts, restored_counts)
    prune_postgres_backups(output_dir, keep)
    print("PostgreSQL 备份验证通过：")
    print(f"- 备份文件：{backup_path}")
    print(f"- 校验表数量：{len(CHECK_TABLES)}")
    print(f"- 校验表总行数：{sum(source_counts.values())}")
    if restore_test_url:
        print("- 恢复演练：已恢复到测试库并通过检查")
    else:
        print("- 恢复演练：未提供测试库连接串，本次只验证备份可读取")
    if archived_assets:
        print(f"- 上传资源包：{asset_backup_path}，条目 {asset_count}")
    elif not no_assets:
        print("- 上传资源包：未发现 uploads 目录，已跳过")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    source_url = args.database_url or database_url()
    summary = runtime_database_summary(source_url or None)
    print("备份与恢复演练")
    print(f"- backend: {summary['backend']}")
    print(f"- database: {summary['database']}")
    try:
        if database_backend(source_url or None) == "postgres":
            check_postgres_backup(
                source_url,
                args.restore_test_database_url.strip(),
                args.output_dir.resolve(),
                args.keep,
                allow_unsafe_restore_target=args.allow_unsafe_restore_target,
                no_assets=args.no_assets,
            )
        else:
            check_sqlite_backup(args.output_dir.resolve(), args.keep, args.no_assets)
    except Exception as exc:
        print(f"备份恢复验证失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
