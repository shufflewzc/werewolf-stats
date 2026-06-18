#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from typing import Any

from db_runtime import connect_runtime_db, database_backend, database_url
from sqlite_store import (
    clear_season_dimension_stats_for_day,
    create_ai_job,
    load_membership_requests,
    load_repository_data,
    load_session_username,
    load_users,
    record_access_log,
    record_ai_conversation,
    require_initialized_database,
    save_membership_requests,
    save_repository_data,
    save_season_dimension_stats,
    save_session,
    save_users,
    update_ai_job_status,
    add_ai_job_step,
)


TEST_PREFIX = "codex_pg_regression_"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a cautious PostgreSQL runtime regression against the configured database.",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="PostgreSQL DATABASE_URL. Defaults to environment variable DATABASE_URL.",
    )
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="Required. The script writes temporary rows and cleans them up.",
    )
    parser.add_argument(
        "--include-rewrite",
        action="store_true",
        help="Also exercise save_repository_data(), which rewrites core repository tables with the same loaded data.",
    )
    return parser.parse_args(argv)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def cleanup_temp_rows(database_url_value: str) -> None:
    with connect_runtime_db(database_url_value) as connection:
        with connection.transaction():
            connection.execute(
                """
                DELETE FROM ai_job_steps
                WHERE job_id IN (SELECT job_id FROM ai_jobs WHERE job_type LIKE ?)
                """,
                (TEST_PREFIX + "%",),
            )
            connection.execute("DELETE FROM ai_jobs WHERE job_type LIKE ?", (TEST_PREFIX + "%",))
            connection.execute("DELETE FROM access_logs WHERE path = ?", ("/postgres-runtime-regression",))
            connection.execute(
                """
                DELETE FROM ai_conversations
                WHERE question = ? OR metadata_json LIKE ?
                """,
                ("postgres regression", "%" + TEST_PREFIX + "%"),
            )
            connection.execute("DELETE FROM app_meta WHERE meta_key LIKE ?", (TEST_PREFIX + "%",))
            connection.execute(
                "DELETE FROM user_sessions WHERE session_token LIKE ?",
                (TEST_PREFIX + "%",),
            )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    database_url_value = (args.database_url or database_url()).strip()
    if database_backend(database_url_value) != "postgres":
        print("回归失败：DATABASE_URL 不是 PostgreSQL。", file=sys.stderr)
        return 2
    if not args.allow_write:
        print("回归失败：需要显式加 --allow-write，避免误写正式库。", file=sys.stderr)
        return 2

    os.environ["DATABASE_URL"] = database_url_value
    os.environ["ENABLE_POSTGRES_READS"] = "1"
    os.environ["ENABLE_POSTGRES_WRITES"] = "1"

    original_users: list[dict[str, Any]] = []
    original_requests: list[dict[str, Any]] = []
    loaded_original_users = False
    loaded_original_requests = False
    temp_username = TEST_PREFIX + secrets.token_hex(6)
    temp_session_token = TEST_PREFIX + secrets.token_hex(12)
    temp_meta_key = TEST_PREFIX + "meta"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    try:
        with connect_runtime_db(database_url_value) as connection:
            require_initialized_database(connection)

        data = load_repository_data()
        original_users = load_users()
        loaded_original_users = True
        original_requests = load_membership_requests()
        loaded_original_requests = True
        assert_true(original_users, "用户表为空，无法测试登录会话。")
        print("1. PostgreSQL 读取通过。")

        base_user = original_users[0]
        temp_user = {
            **base_user,
            "username": temp_username,
            "display_name": "PostgreSQL 回归测试账号",
            "active": True,
            "player_id": None,
            "linked_player_ids": [],
            "manager_scope_keys": [],
            "permissions": [],
            "role": "member",
            "wechat_openid": TEST_PREFIX + secrets.token_hex(8),
            "wechat_web_openid": "",
            "wechat_unionid": "",
        }
        save_users([*original_users, temp_user])
        users_after_create = load_users()
        assert_true(
            any(user["username"] == temp_username for user in users_after_create),
            "临时用户写入后读取不到。",
        )
        print("2. 用户写入通过。")

        save_session(temp_session_token, temp_username)
        assert_true(
            load_session_username(temp_session_token) == temp_username,
            "临时登录会话写入后读取不到。",
        )
        print("3. 登录会话写入通过。")

        from sqlite_store import load_meta_value, save_meta_value

        save_meta_value(temp_meta_key, "ok")
        assert_true(load_meta_value(temp_meta_key) == "ok", "app_meta 写入后读取不到。")
        print("4. app_meta 写入通过。")

        request_id = TEST_PREFIX + secrets.token_hex(6)
        save_membership_requests(
            [
                *original_requests,
                {
                    "request_id": request_id,
                    "request_type": "join_team",
                    "username": temp_username,
                    "display_name": temp_user["display_name"],
                    "player_id": None,
                    "source_team_id": None,
                    "target_team_id": "",
                    "target_guild_id": "",
                    "scope_competition_name": "",
                    "scope_season_name": "",
                    "request_payload": {"source": "postgres_runtime_regression"},
                    "created_on": now,
                },
            ]
        )
        assert_true(
            any(item["request_id"] == request_id for item in load_membership_requests()),
            "审核申请写入后读取不到。",
        )
        print("5. 审核申请写入通过。")

        teams = data.get("teams", [])
        players = data.get("players", [])
        if teams and players:
            team_id = str(teams[0]["team_id"])
            player_id = str(players[0]["player_id"])
            played_on = "2099-12-31"
            save_season_dimension_stats(
                [
                    {
                        "competition_name": TEST_PREFIX + "competition",
                        "season_name": TEST_PREFIX + "season",
                        "played_on": played_on,
                        "player_id": player_id,
                        "team_id": team_id,
                        "seat": 1,
                        "score": 1,
                    }
                ],
                [
                    {
                        "competition_name": TEST_PREFIX + "competition",
                        "season_name": TEST_PREFIX + "season",
                        "played_on": played_on,
                        "team_id": team_id,
                        "seat": 1,
                        "score": 1,
                    }
                ],
            )
            clear_season_dimension_stats_for_day(
                TEST_PREFIX + "competition",
                TEST_PREFIX + "season",
                played_on,
            )
            print("6. 维度数据写入/清理通过。")
        else:
            print("6. 跳过维度数据写入：缺少战队或选手。")

        job_id = create_ai_job(job_type=TEST_PREFIX + "job", created_at=now)
        update_ai_job_status(job_id, status="done", updated_at=now, model="regression")
        step_id = add_ai_job_step(
            job_id=job_id,
            step_order=1,
            step_name=TEST_PREFIX + "step",
            status="done",
            started_at=now,
            finished_at=now,
        )
        assert_true(job_id and step_id, "AI 任务写入失败。")
        print("7. AI 任务写入通过。")

        access_id = record_access_log(
            path="/postgres-runtime-regression",
            method="GET",
            username=temp_username,
            created_at=now,
        )
        conversation_id = record_ai_conversation(
            question="postgres regression",
            answer="ok",
            username=temp_username,
            created_at=now,
            metadata={"source": TEST_PREFIX},
        )
        assert_true(access_id and conversation_id, "日志或 AI 对话写入失败。")
        print("8. 访问日志和 AI 对话写入通过。")

        if args.include_rewrite:
            save_repository_data(data, users_after_create)
            assert_true(load_repository_data()["matches"] is not None, "整体资料保存后读取失败。")
            print("9. 整体资料保存回归通过。")
        else:
            print("9. 跳过整体资料重写；如需测试加 --include-rewrite。")

    except Exception as exc:
        print(f"回归失败：{exc}", file=sys.stderr)
        return 1
    finally:
        try:
            if loaded_original_requests:
                save_membership_requests(original_requests)
            if loaded_original_users:
                save_users(original_users)
            cleanup_temp_rows(database_url_value)
        except Exception as cleanup_exc:
            print(f"清理临时数据失败：{cleanup_exc}", file=sys.stderr)
            return 3

    print("PostgreSQL 运行时回归通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
