#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import backup_restore_check
import production_config_check
import release_check
from db_runtime import database_backend, runtime_database_summary


@dataclass
class Step:
    name: str
    runner: Callable[[], int]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full pre-deploy checklist.")
    parser.add_argument("--database-url", default="", help="Runtime PostgreSQL DATABASE_URL. If omitted, uses env DATABASE_URL.")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Allow local SQLite checks and skip required WeChat credentials.",
    )
    parser.add_argument("--strict-warnings", action="store_true", help="Treat production config warnings as failures.")
    parser.add_argument(
        "--require-miniprogram-data",
        action="store_true",
        help="Fail when miniprogram API contract has no competition data.",
    )
    parser.add_argument("--skip-backup", action="store_true", help="Skip backup readability/restore rehearsal.")
    parser.add_argument("--backup-output-dir", type=Path, default=backup_restore_check.BACKUP_DIR, help="Backup output directory.")
    parser.add_argument("--backup-keep", type=int, default=14, help="Number of recent backups to keep.")
    parser.add_argument("--no-assets", action="store_true", help="Skip uploaded asset archive in SQLite backup mode.")
    parser.add_argument(
        "--restore-test-database-url",
        default="",
        help="Optional empty PostgreSQL database URL used for a real restore rehearsal.",
    )
    parser.add_argument(
        "--allow-unsafe-restore-target",
        action="store_true",
        help="Allow restore rehearsal into a database name that does not look like a test database.",
    )
    return parser.parse_args(argv)


def effective_database_url(args: argparse.Namespace) -> str:
    return args.database_url.strip() or os.getenv("DATABASE_URL", "").strip()


def configure_environment(args: argparse.Namespace, database_url: str) -> None:
    if database_url:
        os.environ["DATABASE_URL"] = database_url
    if database_backend(database_url or None) == "postgres":
        os.environ.setdefault("ENABLE_POSTGRES_WRITES", "1")


def production_config_step(args: argparse.Namespace, database_url: str) -> int:
    check_args: list[str] = []
    if database_url:
        check_args.extend(["--database-url", database_url])
    if args.local:
        check_args.extend(["--allow-sqlite", "--skip-wechat"])
    if args.strict_warnings:
        check_args.append("--strict-warnings")
    return production_config_check.main(check_args)


def release_check_step(args: argparse.Namespace, database_url: str) -> int:
    check_args: list[str] = []
    if database_url:
        check_args.extend(["--database-url", database_url])
    if args.require_miniprogram_data:
        check_args.append("--require-miniprogram-data")
    return release_check.main(check_args)


def backup_check_step(args: argparse.Namespace, database_url: str) -> int:
    check_args: list[str] = []
    if database_url:
        check_args.extend(["--database-url", database_url])
    if args.restore_test_database_url.strip():
        check_args.extend(["--restore-test-database-url", args.restore_test_database_url.strip()])
    check_args.extend(["--output-dir", str(args.backup_output_dir), "--keep", str(args.backup_keep)])
    if args.no_assets:
        check_args.append("--no-assets")
    if args.allow_unsafe_restore_target:
        check_args.append("--allow-unsafe-restore-target")
    return backup_restore_check.main(check_args)


def run_step(step: Step) -> bool:
    print(f"\n== {step.name} ==")
    code = step.runner()
    if code == 0:
        print(f"[OK] {step.name}")
        return True
    print(f"[FAIL] {step.name}", file=sys.stderr)
    return False


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    database_url = effective_database_url(args)
    configure_environment(args, database_url)
    summary = runtime_database_summary(database_url or None)
    print("上线前一键检查")
    print(f"- backend: {summary['backend']}")
    print(f"- database: {summary['database']}")
    if args.local:
        print("- mode: local")
    steps = [
        Step("生产配置体检", lambda: production_config_step(args, database_url)),
        Step("综合发布体检", lambda: release_check_step(args, database_url)),
    ]
    if not args.skip_backup:
        steps.append(Step("备份可读性与恢复检查", lambda: backup_check_step(args, database_url)))
    else:
        print("- backup: skipped")
    failed_steps = [step.name for step in steps if not run_step(step)]
    if failed_steps:
        print("\n上线前检查未通过：", "、".join(failed_steps), file=sys.stderr)
        return 1
    print("\n上线前检查全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
