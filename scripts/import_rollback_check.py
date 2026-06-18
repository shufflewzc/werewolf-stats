#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import sqlite_store
import web_app
from web_app import RequestContext


TEST_MATCH_ID = "zzzzzz-rollbk99-260617-99"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify import batch rollback on a temporary SQLite copy.")
    parser.add_argument(
        "--sqlite-db",
        type=Path,
        default=sqlite_store.DB_PATH,
        help="SQLite database to copy for the rollback self-check.",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep the temporary database copy for inspection.",
    )
    return parser.parse_args(argv)


def admin_ctx() -> RequestContext:
    return RequestContext(
        method="POST",
        path="/matches/new",
        query={},
        form={},
        files={},
        current_user={
            "username": "admin",
            "display_name": "管理员",
            "role": "admin",
            "active": True,
            "province_name": "",
            "region_name": "",
            "permissions": [],
            "manager_scope_keys": [],
        },
        now_label="2026-06-17 00:00:00 中国时间",
        remote_addr="127.0.0.1",
        request_id="req_import_rollback_check",
    )


def patch_runtime_to_sqlite(temp_db: Path) -> dict[str, Any]:
    originals = {
        "sqlite_db_path": sqlite_store.DB_PATH,
        "web_app_db_path": web_app.DB_PATH,
        "postgres_read_mode_enabled": sqlite_store.postgres_read_mode_enabled,
        "postgres_write_mode_enabled": sqlite_store.postgres_write_mode_enabled,
    }
    sqlite_store.DB_PATH = temp_db
    web_app.DB_PATH = temp_db
    sqlite_store.postgres_read_mode_enabled = lambda: False
    sqlite_store.postgres_write_mode_enabled = lambda: False
    web_app.invalidate_validated_data_cache()
    return originals


def restore_runtime(originals: dict[str, Any]) -> None:
    sqlite_store.DB_PATH = originals["sqlite_db_path"]
    web_app.DB_PATH = originals["web_app_db_path"]
    sqlite_store.postgres_read_mode_enabled = originals["postgres_read_mode_enabled"]
    sqlite_store.postgres_write_mode_enabled = originals["postgres_write_mode_enabled"]
    web_app.invalidate_validated_data_cache()


def count_matches(data: dict[str, Any]) -> int:
    return len(data.get("matches") or [])


def has_test_match(data: dict[str, Any]) -> bool:
    return any(match.get("match_id") == TEST_MATCH_ID for match in data.get("matches") or [])


def build_test_match(data: dict[str, Any]) -> dict[str, Any]:
    matches = data.get("matches") or []
    if not matches:
        raise RuntimeError("当前数据库没有比赛记录，无法构造回滚自检数据。")
    test_match = copy.deepcopy(matches[0])
    test_match["match_id"] = TEST_MATCH_ID
    test_match["notes"] = "导入回滚自检临时比赛"
    return test_match


def copy_sqlite_database(source_db: Path, temp_db: Path) -> None:
    source_connection = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    try:
        target_connection = sqlite3.connect(temp_db)
        try:
            source_connection.backup(target_connection)
        finally:
            target_connection.close()
    finally:
        source_connection.close()


def run_check(source_db: Path, *, keep_temp: bool = False) -> str:
    if not source_db.exists():
        raise RuntimeError(f"SQLite 源库不存在：{source_db}")

    temp_dir_context = tempfile.TemporaryDirectory(prefix="werewolf-import-rollback-")
    temp_dir = Path(temp_dir_context.name)
    if keep_temp:
        temp_dir_context.cleanup()
        temp_dir = Path(tempfile.mkdtemp(prefix="werewolf-import-rollback-"))
    try:
        temp_db = temp_dir / source_db.name
        copy_sqlite_database(source_db, temp_db)
        originals = patch_runtime_to_sqlite(temp_db)
        try:
            ctx = admin_ctx()
            initial_data = copy.deepcopy(web_app.load_validated_data())
            initial_count = count_matches(initial_data)
            if has_test_match(initial_data):
                raise RuntimeError(f"源库中已存在自检比赛 ID：{TEST_MATCH_ID}")

            batch_id = web_app.create_import_batch(
                ctx=ctx,
                action="rollback.self_check",
                label="导入回滚自检",
                filename="import_rollback_check.py",
                metadata={"source": "release_check"},
            )

            mutated_data = copy.deepcopy(initial_data)
            mutated_data["matches"].append(build_test_match(initial_data))
            errors = web_app.save_repository_state(mutated_data, web_app.load_users())
            if errors:
                raise RuntimeError("写入自检导入数据失败：" + "；".join(errors[:3]))
            web_app.update_import_batch(
                batch_id,
                status="succeeded",
                summary="自检临时导入 1 场比赛",
                metadata={"matches": 1},
                ctx=ctx,
            )

            imported_data = web_app.load_validated_data()
            if count_matches(imported_data) != initial_count + 1 or not has_test_match(imported_data):
                raise RuntimeError("自检导入未按预期写入临时比赛。")

            ok, message = web_app.rollback_import_batch(batch_id, ctx)
            if not ok:
                raise RuntimeError(message)

            rolled_back_data = web_app.load_validated_data()
            if count_matches(rolled_back_data) != initial_count:
                raise RuntimeError("回滚后比赛数量没有恢复。")
            if has_test_match(rolled_back_data):
                raise RuntimeError("回滚后临时比赛仍然存在。")

            batch = next(
                (item for item in web_app.load_import_batches() if item.get("batch_id") == batch_id),
                None,
            )
            if not batch or batch.get("status") != "rolled_back":
                raise RuntimeError("回滚后导入批次状态没有标记为 rolled_back。")

            if keep_temp:
                return f"{message} 临时库保留在：{temp_db}"
            return message
        finally:
            restore_runtime(originals)
    finally:
        if not keep_temp:
            temp_dir_context.cleanup()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        message = run_check(args.sqlite_db.resolve(), keep_temp=args.keep_temp)
    except Exception as exc:
        print(f"[FAIL] 导入回滚自检失败：{exc}", file=sys.stderr)
        return 1
    print(f"[OK] 导入回滚自检通过：{message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
