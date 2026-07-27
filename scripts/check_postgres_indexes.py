#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from typing import Any

from db_runtime import connect_runtime_db, database_backend, runtime_database_summary


REQUIRED_POSTGRES_INDEXES = {
    "idx_team_members_team_order": ("team_members", ("team_id", "sort_order")),
    "idx_team_members_player": ("team_members", ("player_id",)),
    "idx_teams_scope": ("teams", ("competition_name", "season_name", "active", "name")),
    "idx_teams_guild_scope": ("teams", ("guild_id", "competition_name", "season_name")),
    "idx_players_team_active": ("players", ("team_id", "active", "display_name")),
    "idx_players_display_name": ("players", ("display_name",)),
    "idx_matches_scope_day": ("matches", ("competition_name", "season", "played_on", "round", "game_no")),
    "idx_matches_day": ("matches", ("played_on", "competition_name", "season")),
    "idx_matches_stage": ("matches", ("competition_name", "season", "stage", "group_label")),
    "idx_match_players_match_order": ("match_players", ("match_id", "sort_order")),
    "idx_match_players_player": ("match_players", ("player_id", "match_id")),
    "idx_match_players_team": ("match_players", ("team_id", "match_id")),
    "idx_match_players_camp_result": ("match_players", ("camp", "result")),
    "idx_ai_jobs_created_at": ("ai_jobs", ("created_at",)),
    "idx_ai_job_steps_job_order": ("ai_job_steps", ("job_id", "step_order")),
    "idx_access_logs_created_at": ("access_logs", ("created_at",)),
    "idx_access_logs_path_created_at": ("access_logs", ("path", "created_at")),
    "idx_access_logs_status_created_at": ("access_logs", ("status_code", "created_at")),
    "idx_access_logs_duration_ms": ("access_logs", ("duration_ms",)),
    "idx_access_logs_request_id": ("access_logs", ("request_id",)),
    "idx_web_login_challenges_expires": (
        "web_login_challenges",
        ("expires_at_epoch",),
    ),
    "idx_request_rate_limits_expires": (
        "request_rate_limits",
        ("expires_at_epoch",),
    ),
    "idx_idempotency_keys_expires": (
        "idempotency_keys",
        ("expires_at_epoch",),
    ),
    "idx_import_jobs_status_created": (
        "import_jobs",
        ("status", "created_at"),
    ),
    "idx_audit_logs_created_at": ("audit_logs", ("created_at",)),
    "idx_audit_logs_target": ("audit_logs", ("target_type", "target_id", "created_at")),
    "idx_audit_logs_username": ("audit_logs", ("username", "created_at")),
    "idx_audit_logs_request_id": ("audit_logs", ("request_id",)),
    "idx_ai_conversations_created_at": ("ai_conversations", ("created_at",)),
    "idx_ai_conversations_scope": ("ai_conversations", ("competition_name", "season_name", "created_at")),
    "idx_season_player_dimension_stats_scope": (
        "season_player_dimension_stats",
        ("competition_name", "season_name", "played_on", "player_id"),
    ),
    "idx_season_player_dimension_stats_player_scope": (
        "season_player_dimension_stats",
        ("player_id", "competition_name", "season_name", "played_on"),
    ),
    "idx_season_player_dimension_stats_team_scope": (
        "season_player_dimension_stats",
        ("team_id", "competition_name", "season_name", "played_on"),
    ),
    "idx_season_team_dimension_stats_scope": (
        "season_team_dimension_stats",
        ("competition_name", "season_name", "played_on", "team_id", "seat"),
    ),
    "idx_season_team_dimension_stats_team_scope": (
        "season_team_dimension_stats",
        ("team_id", "competition_name", "season_name", "played_on"),
    ),
    "idx_membership_requests_username": ("membership_requests", ("username", "created_on")),
    "idx_membership_requests_target_team": ("membership_requests", ("target_team_id", "created_on")),
    "idx_membership_requests_scope": (
        "membership_requests",
        ("scope_competition_name", "scope_season_name", "created_on"),
    ),
    "idx_users_player_id": ("users", ("player_id",)),
    "idx_users_wechat_openid": ("users", ("wechat_openid",)),
    "idx_users_wechat_web_openid": ("users", ("wechat_web_openid",)),
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check required PostgreSQL indexes for stable runtime performance.")
    parser.add_argument("--database-url", default="", help="Override DATABASE_URL for this check.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when the runtime database is not PostgreSQL instead of skipping.",
    )
    return parser.parse_args(argv)


def row_value(row: Any, key: str, index: int = 0) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def load_index_columns(connection: Any) -> dict[str, tuple[str, tuple[str, ...]]]:
    rows = connection.execute(
        """
        SELECT
            c.relname AS indexname,
            t.relname AS tablename,
            array_agg(a.attname ORDER BY keys.ordinality) AS columns
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_class t ON t.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS keys(attnum, ordinality) ON TRUE
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = keys.attnum
        WHERE n.nspname = 'public'
        GROUP BY c.relname, t.relname
        """
    ).fetchall()
    indexes: dict[str, tuple[str, tuple[str, ...]]] = {}
    for row in rows:
        columns = row_value(row, "columns", 2) or []
        indexes[str(row_value(row, "indexname", 0))] = (
            str(row_value(row, "tablename", 1)),
            tuple(str(column) for column in columns),
        )
    return indexes


def check_indexes(database_url: str = "", *, strict: bool = False) -> list[str]:
    if database_backend(database_url or None) != "postgres":
        if strict:
            return ["当前运行数据库不是 PostgreSQL，无法检查 PostgreSQL 索引。"]
        print("[SKIP] PostgreSQL 索引检查：当前运行数据库不是 PostgreSQL。")
        return []
    errors: list[str] = []
    with connect_runtime_db(database_url or None) as connection:
        indexes = load_index_columns(connection)
    for index_name, expected in REQUIRED_POSTGRES_INDEXES.items():
        actual = indexes.get(index_name)
        if actual is None:
            errors.append(f"缺少索引：{index_name}")
            continue
        expected_table, expected_columns = expected
        actual_table, actual_columns = actual
        if actual_table != expected_table or actual_columns != expected_columns:
            errors.append(
                f"索引 {index_name} 结构不匹配：当前 {actual_table}({', '.join(actual_columns)})，"
                f"需要 {expected_table}({', '.join(expected_columns)})"
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    summary = runtime_database_summary(args.database_url or None)
    print("PostgreSQL 索引检查：")
    print(f"- backend: {summary['backend']}")
    print(f"- database: {summary['database']}")
    errors = check_indexes(args.database_url, strict=args.strict)
    if errors:
        print("检查未通过：", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        print("请先执行：python3 scripts/apply_postgres_schema.py", file=sys.stderr)
        return 1
    if summary["backend"] == "postgres":
        print(f"检查通过。关键索引数量：{len(REQUIRED_POSTGRES_INDEXES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
