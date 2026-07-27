#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

from sqlite_store import (
    cleanup_expired_logs,
    cleanup_expired_runtime_state,
    cleanup_import_history,
    migrate_legacy_import_history,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean expired backend runtime data.")
    parser.add_argument("--access-retention-days", type=int, default=90)
    parser.add_argument("--audit-retention-days", type=int, default=365)
    parser.add_argument("--import-retention-days", type=int, default=30)
    parser.add_argument("--keep-imports", type=int, default=20)
    parser.add_argument(
        "--purge-legacy-web-login",
        action="store_true",
        help="Delete old web_login:* values from app_meta after schema migration.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = {
        "legacy_imports": migrate_legacy_import_history(),
        "runtime": cleanup_expired_runtime_state(
            purge_legacy_web_login=args.purge_legacy_web_login,
        ),
        "imports": cleanup_import_history(
            retention_days=args.import_retention_days,
            keep_latest=args.keep_imports,
        ),
        "logs": cleanup_expired_logs(
            access_retention_days=args.access_retention_days,
            audit_retention_days=args.audit_retention_days,
        ),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
