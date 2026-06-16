#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sqlite3
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlite_store import DB_PATH, connect_db, ensure_database


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / "data" / "backups"
ASSET_PATHS = [
    ROOT / "assets" / "players" / "uploads",
    ROOT / "assets" / "teams" / "uploads",
]
CHINA_TZ = ZoneInfo("Asia/Shanghai")


def timestamp_label() -> str:
    return datetime.now(CHINA_TZ).strftime("%Y%m%d-%H%M%S")


def backup_database(target_path: Path) -> None:
    ensure_database()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with connect_db() as source:
        with sqlite3.connect(target_path) as target:
            source.backup(target)


def archive_assets(target_path: Path) -> bool:
    existing_paths = [path for path in ASSET_PATHS if path.exists()]
    if not existing_paths:
        return False
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target_path, "w:gz") as archive:
        for path in existing_paths:
            archive.add(path, arcname=str(path.relative_to(ROOT)))
    return True


def prune_backups(backup_dir: Path, keep: int) -> None:
    if keep <= 0 or not backup_dir.exists():
        return
    db_backups = sorted(backup_dir.glob("werewolf_stats-*.db"), key=lambda item: item.name, reverse=True)
    asset_backups = sorted(backup_dir.glob("assets-*.tar.gz"), key=lambda item: item.name, reverse=True)
    for stale_path in db_backups[keep:] + asset_backups[keep:]:
        stale_path.unlink(missing_ok=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a consistent SQLite backup for werewolf-stats.")
    parser.add_argument("--output-dir", type=Path, default=BACKUP_DIR, help="Backup output directory.")
    parser.add_argument("--keep", type=int, default=14, help="Number of recent database and asset backups to keep.")
    parser.add_argument("--no-assets", action="store_true", help="Only back up the SQLite database.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    label = timestamp_label()
    output_dir = args.output_dir.resolve()
    db_backup_path = output_dir / f"werewolf_stats-{label}.db"
    asset_backup_path = output_dir / f"assets-{label}.tar.gz"

    backup_database(db_backup_path)
    archived_assets = False if args.no_assets else archive_assets(asset_backup_path)
    prune_backups(output_dir, args.keep)

    print("备份完成：")
    print(f"- 数据库：{db_backup_path}")
    if archived_assets:
        print(f"- 上传资源：{asset_backup_path}")
    elif not args.no_assets:
        print("- 上传资源：未发现 uploads 目录，已跳过")
    print(f"- 原数据库：{DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
