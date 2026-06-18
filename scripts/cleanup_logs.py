#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import sys

from sqlite_store import cleanup_expired_logs


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean expired access and audit logs.")
    parser.add_argument(
        "--access-days",
        type=int,
        default=int(os.getenv("ACCESS_LOG_RETENTION_DAYS", "30")),
        help="Keep access logs for this many days. Defaults to ACCESS_LOG_RETENTION_DAYS or 30.",
    )
    parser.add_argument(
        "--audit-days",
        type=int,
        default=int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "365")),
        help="Keep audit logs for this many days. Defaults to AUDIT_LOG_RETENTION_DAYS or 365.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print how many rows would be deleted.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    result = cleanup_expired_logs(
        access_retention_days=args.access_days,
        audit_retention_days=args.audit_days,
        dry_run=args.dry_run,
    )
    action = "预计清理" if result["dry_run"] else "已清理"
    print("日志留存清理：")
    print(f"- access_logs 保留 {result['access_retention_days']} 天，截止日期 {result['access_cutoff_date']}，{action} {result['deleted_access_logs']} 条")
    print(f"- audit_logs 保留 {result['audit_retention_days']} 天，截止日期 {result['audit_cutoff_date']}，{action} {result['deleted_audit_logs']} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
