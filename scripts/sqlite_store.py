#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from schema_version import REQUIRED_SCHEMA_VERSION, SCHEMA_VERSION_META_KEY
from web_authz import DEFAULT_EVENT_MANAGER_PERMISSION_KEYS


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "werewolf_stats.db"
DEFAULT_USER_PHOTO = "assets/players/default-player.svg"
SQLITE_BUSY_TIMEOUT_MS = int(os.getenv("SQLITE_BUSY_TIMEOUT_MS", "5000"))
SQLITE_JOURNAL_MODE = os.getenv("SQLITE_JOURNAL_MODE", "WAL").strip().upper()
SQLITE_SYNCHRONOUS = os.getenv("SQLITE_SYNCHRONOUS", "NORMAL").strip().upper()
LOG_CLEANUP_META_KEY = "log_cleanup:last_run"


def normalize_stance_result(entry: dict[str, Any]) -> str:
    value = str(entry.get("stance_result") or "").strip()
    if value in {"correct", "incorrect", "none"}:
        return value
    legacy_pick = str(entry.get("stance_pick") or "none").strip()
    if not legacy_pick or legacy_pick == "none":
        return "none"
    return "correct" if entry.get("stance_correct") else "incorrect"


def to_legacy_stance_columns(
    stance_result: str,
    winning_camp: str,
) -> tuple[str, int]:
    if stance_result == "correct":
        return winning_camp, 1
    if stance_result == "incorrect":
        legacy_pick = "werewolves" if winning_camp == "villagers" else "villagers"
        return legacy_pick, 0
    return "none", 0


MATCH_SCORE_MODEL_STANDARD = "standard"
MATCH_SCORE_MODEL_JINGCHENG_DAILY = "jingcheng_daily"
MATCH_SCORE_COMPONENT_FIELDS = [
    "result_points",
    "vote_points",
    "behavior_points",
    "special_points",
    "adjustment_points",
]


def normalize_match_score_model(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized == MATCH_SCORE_MODEL_JINGCHENG_DAILY:
        return normalized
    return MATCH_SCORE_MODEL_STANDARD


def uses_structured_score_model(value: Any) -> bool:
    return normalize_match_score_model(value) == MATCH_SCORE_MODEL_JINGCHENG_DAILY


def normalize_score_breakdown(entry: dict[str, Any]) -> dict[str, float]:
    raw_breakdown = entry.get("score_breakdown")
    breakdown = {
        str(field_name): float(value or 0.0)
        for field_name, value in raw_breakdown.items()
        if str(field_name).strip()
    } if isinstance(raw_breakdown, dict) else {}
    for field_name in MATCH_SCORE_COMPONENT_FIELDS:
        breakdown[field_name] = float(
            entry.get(field_name, breakdown.get(field_name, 0.0)) or 0.0
        )
    return breakdown


def calculate_score_breakdown_total(
    entry: dict[str, Any],
    scoring_rule: dict[str, Any] | None = None,
) -> float:
    breakdown = normalize_score_breakdown(entry)
    component_keys = MATCH_SCORE_COMPONENT_FIELDS
    if isinstance(scoring_rule, dict):
        configured_keys = [
            str(component.get("key") or "").strip()
            for component in scoring_rule.get("components", [])
            if isinstance(component, dict) and component.get("enabled", False)
        ]
        if configured_keys:
            component_keys = configured_keys
    return round(sum(float(breakdown.get(key, 0.0)) for key in component_keys), 2)


def derive_match_awards(
    participants: list[dict[str, Any]],
    winning_camp: str,
) -> tuple[str, str, str]:
    valid_participants = [
        participant
        for participant in participants
        if str(participant.get("player_id") or "").strip()
    ]
    sorted_by_points = sorted(
        valid_participants,
        key=lambda item: (
            -float(item.get("points_earned") or 0.0),
            int(item.get("seat") or 0),
            str(item.get("player_id") or ""),
        ),
    )
    mvp_player_id = sorted_by_points[0]["player_id"] if sorted_by_points else ""
    svp_player_id = next(
        (
            participant["player_id"]
            for participant in sorted_by_points
            if participant["player_id"] != mvp_player_id
        ),
        "",
    )
    scapegoat_player_id = ""
    if winning_camp == "werewolves":
        scapegoat_candidates = [
            participant
            for participant in valid_participants
            if str(participant.get("camp") or "").strip() != winning_camp
        ]
        scapegoat_sorted = sorted(
            scapegoat_candidates,
            key=lambda item: (
                float(item.get("points_earned") or 0.0),
                int(item.get("seat") or 0),
                str(item.get("player_id") or ""),
            ),
        )
        scapegoat_player_id = (
            scapegoat_sorted[0]["player_id"] if scapegoat_sorted else ""
        )
    return mvp_player_id, svp_player_id, scapegoat_player_id


def connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=max(1.0, SQLITE_BUSY_TIMEOUT_MS / 1000))
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA foreign_keys = ON")
    if SQLITE_JOURNAL_MODE:
        connection.execute(f"PRAGMA journal_mode = {SQLITE_JOURNAL_MODE}")
    if SQLITE_SYNCHRONOUS:
        connection.execute(f"PRAGMA synchronous = {SQLITE_SYNCHRONOUS}")
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            active INTEGER NOT NULL CHECK (active IN (0, 1)),
            player_id TEXT UNIQUE,
            linked_player_ids_json TEXT NOT NULL DEFAULT '[]',
            manager_scope_keys_json TEXT NOT NULL DEFAULT '[]',
            permissions_json TEXT NOT NULL DEFAULT '[]',
            role TEXT NOT NULL DEFAULT 'member',
            province_name TEXT NOT NULL DEFAULT '',
            region_name TEXT NOT NULL DEFAULT '',
            gender TEXT NOT NULL DEFAULT '',
            bio TEXT NOT NULL DEFAULT '',
            photo TEXT NOT NULL DEFAULT 'assets/players/default-player.svg',
            wechat_openid TEXT NOT NULL DEFAULT '',
            wechat_web_openid TEXT NOT NULL DEFAULT '',
            wechat_unionid TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS app_meta (
            meta_key TEXT PRIMARY KEY,
            meta_value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ai_jobs (
            job_id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            scope_type TEXT NOT NULL DEFAULT '',
            scope_key TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            model TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            error_message TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS ai_job_steps (
            step_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            step_order INTEGER NOT NULL,
            step_name TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL DEFAULT '',
            input_summary TEXT NOT NULL DEFAULT '',
            output_summary TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (job_id) REFERENCES ai_jobs(job_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS access_logs (
            log_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL DEFAULT '',
            path TEXT NOT NULL,
            method TEXT NOT NULL,
            status_code INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            query_string TEXT NOT NULL DEFAULT '',
            username TEXT NOT NULL DEFAULT '',
            ip_address TEXT NOT NULL DEFAULT '',
            user_agent TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            audit_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL DEFAULT '',
            username TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL,
            target_type TEXT NOT NULL DEFAULT '',
            target_id TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            ip_address TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS ai_conversations (
            conversation_id TEXT PRIMARY KEY,
            competition_name TEXT NOT NULL DEFAULT '',
            season_name TEXT NOT NULL DEFAULT '',
            region_name TEXT NOT NULL DEFAULT '',
            series_slug TEXT NOT NULL DEFAULT '',
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            model TEXT NOT NULL DEFAULT '',
            username TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS user_sessions (
            session_token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS guilds (
            guild_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            short_name TEXT NOT NULL,
            logo TEXT NOT NULL,
            active INTEGER NOT NULL CHECK (active IN (0, 1)),
            founded_on TEXT NOT NULL,
            leader_username TEXT NOT NULL,
            manager_usernames_json TEXT NOT NULL DEFAULT '[]',
            honors_json TEXT NOT NULL DEFAULT '[]',
            notes TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS teams (
            team_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            short_name TEXT NOT NULL,
            logo TEXT NOT NULL,
            active INTEGER NOT NULL CHECK (active IN (0, 1)),
            founded_on TEXT NOT NULL,
            competition_name TEXT NOT NULL DEFAULT '',
            season_name TEXT NOT NULL DEFAULT '',
            guild_id TEXT NOT NULL DEFAULT '',
            captain_player_id TEXT,
            stage_groups_json TEXT NOT NULL DEFAULT '[]',
            notes TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS team_members (
            team_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            sort_order INTEGER NOT NULL,
            PRIMARY KEY (team_id, player_id),
            FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS players (
            player_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            team_id TEXT NOT NULL,
            photo TEXT NOT NULL,
            aliases_json TEXT NOT NULL,
            active INTEGER NOT NULL CHECK (active IN (0, 1)),
            joined_on TEXT NOT NULL,
            notes TEXT NOT NULL,
            FOREIGN KEY (team_id) REFERENCES teams(team_id)
        );

        CREATE TABLE IF NOT EXISTS matches (
            match_id TEXT PRIMARY KEY,
            competition_name TEXT NOT NULL,
            season TEXT NOT NULL,
            stage TEXT NOT NULL,
            round INTEGER NOT NULL,
            game_no INTEGER NOT NULL,
            score_model TEXT NOT NULL DEFAULT 'standard',
            scoring_rule_json TEXT NOT NULL DEFAULT '{}',
            exclude_from_team_scores INTEGER NOT NULL DEFAULT 0,
            played_on TEXT NOT NULL,
            group_label TEXT NOT NULL DEFAULT '',
            table_label TEXT NOT NULL,
            format TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            winning_camp TEXT NOT NULL,
            mvp_player_id TEXT NOT NULL DEFAULT '',
            svp_player_id TEXT NOT NULL DEFAULT '',
            scapegoat_player_id TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS match_players (
            match_id TEXT NOT NULL,
            sort_order INTEGER NOT NULL,
            player_id TEXT NOT NULL,
            team_id TEXT NOT NULL,
            seat INTEGER NOT NULL,
            role TEXT NOT NULL,
            camp TEXT NOT NULL,
            survived INTEGER NOT NULL CHECK (survived IN (0, 1)),
            result TEXT NOT NULL,
            points_earned REAL NOT NULL,
            result_points REAL NOT NULL DEFAULT 0,
            vote_points REAL NOT NULL DEFAULT 0,
            behavior_points REAL NOT NULL DEFAULT 0,
            special_points REAL NOT NULL DEFAULT 0,
            adjustment_points REAL NOT NULL DEFAULT 0,
            score_breakdown_json TEXT NOT NULL DEFAULT '{}',
            points_available REAL NOT NULL,
            stance_pick TEXT NOT NULL,
            stance_correct INTEGER NOT NULL CHECK (stance_correct IN (0, 1)),
            notes TEXT NOT NULL,
            PRIMARY KEY (match_id, sort_order),
            FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES players(player_id),
            FOREIGN KEY (team_id) REFERENCES teams(team_id)
        );

        CREATE INDEX IF NOT EXISTS idx_team_members_team_order
        ON team_members(team_id, sort_order);

        CREATE INDEX IF NOT EXISTS idx_match_players_match_order
        ON match_players(match_id, sort_order);

        CREATE INDEX IF NOT EXISTS idx_ai_jobs_created_at
        ON ai_jobs(created_at);

        CREATE INDEX IF NOT EXISTS idx_ai_job_steps_job_order
        ON ai_job_steps(job_id, step_order);

        CREATE INDEX IF NOT EXISTS idx_access_logs_created_at
        ON access_logs(created_at);

        CREATE INDEX IF NOT EXISTS idx_access_logs_path_created_at
        ON access_logs(path, created_at);

        CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at
        ON audit_logs(created_at);

        CREATE INDEX IF NOT EXISTS idx_audit_logs_target
        ON audit_logs(target_type, target_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_audit_logs_username
        ON audit_logs(username, created_at);

        CREATE INDEX IF NOT EXISTS idx_audit_logs_request_id
        ON audit_logs(request_id);

        CREATE INDEX IF NOT EXISTS idx_ai_conversations_created_at
        ON ai_conversations(created_at);

        CREATE INDEX IF NOT EXISTS idx_ai_conversations_scope
        ON ai_conversations(competition_name, season_name, created_at);

        CREATE TABLE IF NOT EXISTS season_player_dimension_stats (
            competition_name TEXT NOT NULL,
            season_name TEXT NOT NULL,
            played_on TEXT NOT NULL,
            player_id TEXT NOT NULL,
            team_id TEXT NOT NULL,
            seat INTEGER NOT NULL DEFAULT 0,
            metrics_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (competition_name, season_name, played_on, player_id),
            FOREIGN KEY (player_id) REFERENCES players(player_id) ON DELETE CASCADE,
            FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS season_team_dimension_stats (
            competition_name TEXT NOT NULL,
            season_name TEXT NOT NULL,
            played_on TEXT NOT NULL,
            team_id TEXT NOT NULL,
            seat INTEGER NOT NULL DEFAULT 0,
            metrics_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (competition_name, season_name, played_on, team_id, seat),
            FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_season_player_dimension_stats_scope
        ON season_player_dimension_stats(competition_name, season_name, played_on, player_id);

        CREATE INDEX IF NOT EXISTS idx_season_team_dimension_stats_scope
        ON season_team_dimension_stats(competition_name, season_name, played_on, team_id, seat);

        CREATE TABLE IF NOT EXISTS membership_requests (
            request_id TEXT PRIMARY KEY,
            request_type TEXT NOT NULL,
            username TEXT NOT NULL,
            display_name TEXT NOT NULL,
            player_id TEXT,
            source_team_id TEXT,
            target_team_id TEXT NOT NULL,
            target_guild_id TEXT NOT NULL DEFAULT '',
            scope_competition_name TEXT NOT NULL DEFAULT '',
            scope_season_name TEXT NOT NULL DEFAULT '',
            request_payload_json TEXT NOT NULL DEFAULT '{}',
            created_on TEXT NOT NULL
        );

        """
    )
    ensure_schema_migrations(connection)
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_player_id
        ON users(player_id)
        WHERE player_id IS NOT NULL
        """
    )
    connection.commit()


def ensure_schema_migrations(connection: sqlite3.Connection) -> None:
    user_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()
    }
    if "player_id" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN player_id TEXT")
    if "linked_player_ids_json" not in user_columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN linked_player_ids_json TEXT NOT NULL DEFAULT '[]'"
        )
    if "manager_scope_keys_json" not in user_columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN manager_scope_keys_json TEXT NOT NULL DEFAULT '[]'"
        )
    if "permissions_json" not in user_columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN permissions_json TEXT NOT NULL DEFAULT '[]'"
        )
    if "role" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'member'")
        connection.execute(
            "UPDATE users SET role = 'admin' WHERE username = 'admin'"
        )
        connection.execute(
            "UPDATE users SET role = 'member' WHERE role IS NULL OR role = ''"
        )
    updated_user_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()
    }
    if "permissions_json" in updated_user_columns and "role" in updated_user_columns:
        connection.execute(
            """
            UPDATE users
            SET permissions_json = ?
            WHERE role = 'event_manager'
              AND (permissions_json IS NULL OR permissions_json = '' OR permissions_json = '[]')
            """,
            (json.dumps(DEFAULT_EVENT_MANAGER_PERMISSION_KEYS, ensure_ascii=False),),
        )
    if "province_name" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN province_name TEXT NOT NULL DEFAULT ''")
    if "region_name" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN region_name TEXT NOT NULL DEFAULT ''")
    if "gender" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN gender TEXT NOT NULL DEFAULT ''")
    if "bio" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN bio TEXT NOT NULL DEFAULT ''")
    if "photo" not in user_columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN photo TEXT NOT NULL DEFAULT 'assets/players/default-player.svg'"
        )
    if "wechat_openid" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN wechat_openid TEXT NOT NULL DEFAULT ''")
    if "wechat_web_openid" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN wechat_web_openid TEXT NOT NULL DEFAULT ''")
    if "wechat_unionid" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN wechat_unionid TEXT NOT NULL DEFAULT ''")
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_wechat_openid
        ON users(wechat_openid)
        WHERE wechat_openid != ''
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_wechat_web_openid
        ON users(wechat_web_openid)
        WHERE wechat_web_openid != ''
        """
    )
    access_log_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(access_logs)").fetchall()
    }
    if access_log_columns and "request_id" not in access_log_columns:
        connection.execute("ALTER TABLE access_logs ADD COLUMN request_id TEXT NOT NULL DEFAULT ''")
    if access_log_columns and "status_code" not in access_log_columns:
        connection.execute("ALTER TABLE access_logs ADD COLUMN status_code INTEGER NOT NULL DEFAULT 0")
    if access_log_columns and "duration_ms" not in access_log_columns:
        connection.execute("ALTER TABLE access_logs ADD COLUMN duration_ms INTEGER NOT NULL DEFAULT 0")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_access_logs_status_created_at
        ON access_logs(status_code, created_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_access_logs_duration_ms
        ON access_logs(duration_ms)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_access_logs_request_id
        ON access_logs(request_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_logs_request_id
        ON audit_logs(request_id)
        """
    )
    guild_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(guilds)").fetchall()
    }
    if guild_columns:
        if "manager_usernames_json" not in guild_columns:
            connection.execute(
                "ALTER TABLE guilds ADD COLUMN manager_usernames_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "honors_json" not in guild_columns:
            connection.execute(
                "ALTER TABLE guilds ADD COLUMN honors_json TEXT NOT NULL DEFAULT '[]'"
            )
    team_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(teams)").fetchall()
    }
    if "competition_name" not in team_columns:
        connection.execute(
            "ALTER TABLE teams ADD COLUMN competition_name TEXT NOT NULL DEFAULT ''"
        )
    if "season_name" not in team_columns:
        connection.execute(
            "ALTER TABLE teams ADD COLUMN season_name TEXT NOT NULL DEFAULT ''"
        )
    if "guild_id" not in team_columns:
        connection.execute("ALTER TABLE teams ADD COLUMN guild_id TEXT NOT NULL DEFAULT ''")
    if "captain_player_id" not in team_columns:
        connection.execute("ALTER TABLE teams ADD COLUMN captain_player_id TEXT")
    if "stage_groups_json" not in team_columns:
        connection.execute(
            "ALTER TABLE teams ADD COLUMN stage_groups_json TEXT NOT NULL DEFAULT '[]'"
        )
    match_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(matches)").fetchall()
    }
    if "competition_name" not in match_columns:
        connection.execute("ALTER TABLE matches ADD COLUMN competition_name TEXT")
        connection.execute(
            "UPDATE matches SET competition_name = season WHERE competition_name IS NULL OR competition_name = ''"
        )
    if "group_label" not in match_columns:
        connection.execute(
            "ALTER TABLE matches ADD COLUMN group_label TEXT NOT NULL DEFAULT ''"
        )
        connection.execute(
            "UPDATE matches SET group_label = 'A组' WHERE group_label IS NULL OR group_label = ''"
        )
    if "mvp_player_id" not in match_columns:
        connection.execute(
            "ALTER TABLE matches ADD COLUMN mvp_player_id TEXT NOT NULL DEFAULT ''"
        )
    if "svp_player_id" not in match_columns:
        connection.execute(
            "ALTER TABLE matches ADD COLUMN svp_player_id TEXT NOT NULL DEFAULT ''"
        )
    if "scapegoat_player_id" not in match_columns:
        connection.execute(
            "ALTER TABLE matches ADD COLUMN scapegoat_player_id TEXT NOT NULL DEFAULT ''"
        )
    if "score_model" not in match_columns:
        connection.execute(
            "ALTER TABLE matches ADD COLUMN score_model TEXT NOT NULL DEFAULT 'standard'"
        )
    if "scoring_rule_json" not in match_columns:
        connection.execute(
            "ALTER TABLE matches ADD COLUMN scoring_rule_json TEXT NOT NULL DEFAULT '{}'"
        )
    if "exclude_from_team_scores" not in match_columns:
        connection.execute(
            "ALTER TABLE matches ADD COLUMN exclude_from_team_scores INTEGER NOT NULL DEFAULT 0"
        )
    match_player_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(match_players)").fetchall()
    }
    for column_name in MATCH_SCORE_COMPONENT_FIELDS:
        if column_name not in match_player_columns:
            connection.execute(
                f"ALTER TABLE match_players ADD COLUMN {column_name} REAL NOT NULL DEFAULT 0"
            )
    if "score_breakdown_json" not in match_player_columns:
        connection.execute(
            "ALTER TABLE match_players ADD COLUMN score_breakdown_json TEXT NOT NULL DEFAULT '{}'"
        )
    request_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(membership_requests)").fetchall()
    }
    if "request_payload_json" not in request_columns:
        connection.execute(
            "ALTER TABLE membership_requests ADD COLUMN request_payload_json TEXT NOT NULL DEFAULT '{}'"
        )
    if "target_guild_id" not in request_columns:
        connection.execute(
            "ALTER TABLE membership_requests ADD COLUMN target_guild_id TEXT NOT NULL DEFAULT ''"
        )
    if "scope_competition_name" not in request_columns:
        connection.execute(
            "ALTER TABLE membership_requests ADD COLUMN scope_competition_name TEXT NOT NULL DEFAULT ''"
        )
    if "scope_season_name" not in request_columns:
        connection.execute(
            "ALTER TABLE membership_requests ADD COLUMN scope_season_name TEXT NOT NULL DEFAULT ''"
        )
    migrate_season_team_dimension_stats_schema(connection)
    backfill_team_scopes(connection)
    backfill_match_awards(connection)
    backfill_team_claim_captains(connection)
    connection.execute(
        """
        INSERT INTO app_meta (meta_key, meta_value)
        VALUES (?, ?)
        ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
        """,
        (SCHEMA_VERSION_META_KEY, str(REQUIRED_SCHEMA_VERSION)),
    )


def migrate_season_team_dimension_stats_schema(connection: sqlite3.Connection) -> None:
    table_columns = connection.execute(
        "PRAGMA table_info(season_team_dimension_stats)"
    ).fetchall()
    if not table_columns:
        return
    pk_columns = [
        row["name"]
        for row in sorted(table_columns, key=lambda item: int(item["pk"] or 0))
        if int(row["pk"] or 0) > 0
    ]
    expected_pk_columns = [
        "competition_name",
        "season_name",
        "played_on",
        "team_id",
        "seat",
    ]
    if pk_columns == expected_pk_columns:
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_season_team_dimension_stats_scope
            ON season_team_dimension_stats(competition_name, season_name, played_on, team_id, seat)
            """
        )
        return

    existing_rows = connection.execute(
        """
        SELECT competition_name, season_name, played_on, team_id, seat, metrics_json
        FROM season_team_dimension_stats
        ORDER BY competition_name, season_name, played_on, team_id, seat, rowid
        """
    ).fetchall()
    deduped_rows: dict[tuple[str, str, str, str, int], sqlite3.Row] = {}
    for row in existing_rows:
        key = (
            row["competition_name"],
            row["season_name"],
            row["played_on"],
            row["team_id"],
            int(row["seat"] or 0),
        )
        deduped_rows[key] = row

    connection.execute("DROP INDEX IF EXISTS idx_season_team_dimension_stats_scope")
    connection.execute("ALTER TABLE season_team_dimension_stats RENAME TO season_team_dimension_stats_legacy")
    connection.execute(
        """
        CREATE TABLE season_team_dimension_stats (
            competition_name TEXT NOT NULL,
            season_name TEXT NOT NULL,
            played_on TEXT NOT NULL,
            team_id TEXT NOT NULL,
            seat INTEGER NOT NULL DEFAULT 0,
            metrics_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (competition_name, season_name, played_on, team_id, seat),
            FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_season_team_dimension_stats_scope
        ON season_team_dimension_stats(competition_name, season_name, played_on, team_id, seat)
        """
    )
    for row in deduped_rows.values():
        connection.execute(
            """
            INSERT INTO season_team_dimension_stats (
                competition_name, season_name, played_on, team_id, seat, metrics_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row["competition_name"],
                row["season_name"],
                row["played_on"],
                row["team_id"],
                int(row["seat"] or 0),
                row["metrics_json"] or "{}",
            ),
        )
    connection.execute("DROP TABLE season_team_dimension_stats_legacy")


def backfill_team_scopes(connection: sqlite3.Connection) -> None:
    team_rows = connection.execute(
        """
        SELECT team_id, competition_name, season_name
        FROM teams
        ORDER BY team_id
        """
    ).fetchall()
    scoped_matches = connection.execute(
        """
        SELECT mp.team_id, m.competition_name, m.season
        FROM match_players AS mp
        JOIN matches AS m ON m.match_id = mp.match_id
        ORDER BY m.played_on, m.round, m.game_no, m.match_id, mp.sort_order
        """
    ).fetchall()
    scope_by_team: dict[str, tuple[str, str]] = {}
    for row in scoped_matches:
        team_id = str(row["team_id"] or "").strip()
        if not team_id or team_id in scope_by_team:
            continue
        scope_by_team[team_id] = (
            str(row["competition_name"] or "").strip(),
            str(row["season"] or "").strip(),
        )

    for row in team_rows:
        team_id = row["team_id"]
        current_competition_name = str(row["competition_name"] or "").strip()
        current_season_name = str(row["season_name"] or "").strip()
        derived_competition_name, derived_season_name = scope_by_team.get(
            team_id,
            (current_competition_name, current_season_name),
        )
        next_competition_name = (
            current_competition_name or derived_competition_name or "历史未分配赛事"
        )
        next_season_name = current_season_name or derived_season_name or "历史未分配赛季"
        if (
            next_competition_name != current_competition_name
            or next_season_name != current_season_name
        ):
            connection.execute(
                """
                UPDATE teams
                SET competition_name = ?, season_name = ?
                WHERE team_id = ?
                """,
                (next_competition_name, next_season_name, team_id),
            )


def backfill_match_awards(connection: sqlite3.Connection) -> None:
    match_rows = connection.execute(
        """
        SELECT match_id, winning_camp, mvp_player_id, svp_player_id, scapegoat_player_id
        FROM matches
        ORDER BY match_id
        """
    ).fetchall()
    participant_rows = connection.execute(
        """
        SELECT match_id, player_id, seat, camp, points_earned
        FROM match_players
        ORDER BY match_id, sort_order
        """
    ).fetchall()
    participants_by_match: dict[str, list[dict[str, Any]]] = {}
    for row in participant_rows:
        participants_by_match.setdefault(row["match_id"], []).append(
            {
                "player_id": row["player_id"],
                "seat": row["seat"],
                "camp": row["camp"],
                "points_earned": float(row["points_earned"]),
            }
        )

    for row in match_rows:
        derived_mvp, derived_svp, derived_scapegoat = derive_match_awards(
            participants_by_match.get(row["match_id"], []),
            row["winning_camp"],
        )
        next_mvp = str(row["mvp_player_id"] or "").strip() or derived_mvp
        next_svp = str(row["svp_player_id"] or "").strip() or derived_svp
        next_scapegoat = ""
        if row["winning_camp"] == "werewolves":
            next_scapegoat = (
                str(row["scapegoat_player_id"] or "").strip() or derived_scapegoat
            )
        if (
            next_mvp != str(row["mvp_player_id"] or "")
            or next_svp != str(row["svp_player_id"] or "")
            or next_scapegoat != str(row["scapegoat_player_id"] or "")
        ):
            connection.execute(
                """
                UPDATE matches
                SET mvp_player_id = ?, svp_player_id = ?, scapegoat_player_id = ?
                WHERE match_id = ?
                """,
                (
                    next_mvp,
                    next_svp,
                    next_scapegoat,
                    row["match_id"],
                ),
            )


def backfill_team_claim_captains(connection: sqlite3.Connection) -> None:
    user_rows = connection.execute(
        """
        SELECT player_id, linked_player_ids_json
        FROM users
        """
    ).fetchall()
    bound_player_ids: set[str] = set()
    for row in user_rows:
        primary_player_id = str(row["player_id"] or "").strip()
        if primary_player_id:
            bound_player_ids.add(primary_player_id)
        try:
            linked_player_ids = json.loads(row["linked_player_ids_json"] or "[]")
        except json.JSONDecodeError:
            linked_player_ids = []
        for player_id in linked_player_ids:
            normalized_player_id = str(player_id or "").strip()
            if normalized_player_id:
                bound_player_ids.add(normalized_player_id)

    team_rows = connection.execute(
        """
        SELECT team_id, captain_player_id
        FROM teams
        WHERE captain_player_id IS NOT NULL AND captain_player_id != ''
        """
    ).fetchall()
    stale_team_ids = [
        row["team_id"]
        for row in team_rows
        if str(row["captain_player_id"] or "").strip() not in bound_player_ids
    ]
    if not stale_team_ids:
        return
    connection.executemany(
        "UPDATE teams SET captain_player_id = NULL WHERE team_id = ?",
        [(team_id,) for team_id in stale_team_ids],
    )


def database_is_initialized(connection: Any) -> bool:
    cursor = connection.execute(
        "SELECT meta_value FROM app_meta WHERE meta_key = 'initialized'"
    )
    row = cursor.fetchone()
    return bool(row and row["meta_value"] == "1")


def connection_backend(connection: Any) -> str:
    return str(getattr(connection, "backend", "sqlite") or "sqlite")


def transaction_context(connection: Any) -> Any:
    transaction = getattr(connection, "transaction", None)
    if transaction:
        return transaction()
    return connection


def china_today_iso() -> str:
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).date().isoformat()


def china_date_days_ago(days: int) -> str:
    safe_days = max(0, int(days or 0))
    return (
        datetime.now(timezone.utc)
        .astimezone(timezone(timedelta(hours=8)))
        .date()
        - timedelta(days=safe_days)
    ).isoformat()


def replace_repository_data(
    connection: Any,
    teams: list[dict[str, Any]],
    players: list[dict[str, Any]],
    matches: list[dict[str, Any]],
    users: list[dict[str, Any]],
    guilds: list[dict[str, Any]] | None = None,
) -> None:
    guild_rows = guilds or []
    backend = connection_backend(connection)
    existing_sessions = connection.execute(
        """
        SELECT session_token, username, created_at
        FROM user_sessions
        """
    ).fetchall()
    if backend == "sqlite":
        connection.execute("PRAGMA foreign_keys = OFF")
    with transaction_context(connection):
        connection.execute("DELETE FROM match_players")
        connection.execute("DELETE FROM matches")
        connection.execute("DELETE FROM team_members")
        connection.execute("DELETE FROM players")
        connection.execute("DELETE FROM teams")
        connection.execute("DELETE FROM guilds")
        connection.execute("DELETE FROM user_sessions")
        connection.execute("DELETE FROM users")

        for user in users:
            connection.execute(
                """
                INSERT INTO users (
                    username, display_name, password_salt, password_hash, active, player_id,
                    linked_player_ids_json, manager_scope_keys_json, permissions_json, role,
                    province_name, region_name, gender, bio, photo,
                    wechat_openid, wechat_web_openid, wechat_unionid
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["username"],
                    user.get("display_name") or user["username"],
                    user["password_salt"],
                    user["password_hash"],
                    1 if user.get("active") else 0,
                    user.get("player_id"),
                    json.dumps(user.get("linked_player_ids", []), ensure_ascii=False),
                    json.dumps(user.get("manager_scope_keys", []), ensure_ascii=False),
                    json.dumps(user.get("permissions", []), ensure_ascii=False),
                    user.get("role") or ("admin" if user["username"] == "admin" else "member"),
                    user.get("province_name") or "",
                    user.get("region_name") or "",
                    user.get("gender") or "",
                    user.get("bio") or "",
                    user.get("photo") or DEFAULT_USER_PHOTO,
                    user.get("wechat_openid") or "",
                    user.get("wechat_web_openid") or "",
                    user.get("wechat_unionid") or "",
                ),
            )

        valid_usernames = {
            str(user.get("username") or "").strip()
            for user in users
            if str(user.get("username") or "").strip()
        }
        for row in existing_sessions:
            username = str(row["username"] or "").strip()
            session_token = str(row["session_token"] or "").strip()
            created_at = str(row["created_at"] or "").strip()
            if not username or not session_token or username not in valid_usernames:
                continue
            connection.execute(
                """
                INSERT INTO user_sessions (session_token, username, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_token) DO UPDATE SET
                    username = excluded.username,
                    created_at = excluded.created_at
                """,
                (
                    session_token,
                    username,
                    created_at,
                ),
            )

        for guild in guild_rows:
            connection.execute(
                """
                INSERT INTO guilds (
                    guild_id, name, short_name, logo, active, founded_on,
                    leader_username, manager_usernames_json, honors_json, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild["guild_id"],
                    guild["name"],
                    guild["short_name"],
                    guild["logo"],
                    1 if guild.get("active") else 0,
                    guild["founded_on"],
                    guild["leader_username"],
                    json.dumps(guild.get("manager_usernames", []), ensure_ascii=False),
                    json.dumps(guild.get("honors", []), ensure_ascii=False),
                    guild["notes"],
                ),
            )

        for team in teams:
            connection.execute(
                """
                INSERT INTO teams (
                    team_id, name, short_name, logo, active, founded_on,
                    competition_name, season_name, guild_id, captain_player_id, stage_groups_json, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    team["team_id"],
                    team["name"],
                    team["short_name"],
                    team["logo"],
                    1 if team.get("active") else 0,
                    team["founded_on"],
                    team.get("competition_name", ""),
                    team.get("season_name", ""),
                    team.get("guild_id", ""),
                    team.get("captain_player_id"),
                    json.dumps(team.get("stage_groups", []), ensure_ascii=False),
                    team["notes"],
                ),
            )

        for player in players:
            connection.execute(
                """
                INSERT INTO players (
                    player_id, display_name, team_id, photo, aliases_json, active, joined_on, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    player["player_id"],
                    player["display_name"],
                    player["team_id"],
                    player["photo"],
                    json.dumps(player["aliases"], ensure_ascii=False),
                    1 if player.get("active") else 0,
                    player["joined_on"],
                    player["notes"],
                ),
            )

        for team in teams:
            for sort_order, player_id in enumerate(team["members"]):
                connection.execute(
                    """
                    INSERT INTO team_members (team_id, player_id, sort_order)
                    VALUES (?, ?, ?)
                    """,
                    (team["team_id"], player_id, sort_order),
                )

        for match in matches:
            connection.execute(
                """
                INSERT INTO matches (
                    match_id, competition_name, season, stage, round, game_no, score_model, scoring_rule_json, exclude_from_team_scores, played_on, group_label, table_label, format,
                    duration_minutes, winning_camp, mvp_player_id, svp_player_id, scapegoat_player_id, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match["match_id"],
                    match.get("competition_name") or match["season"],
                    match["season"],
                    match["stage"],
                    match["round"],
                    match["game_no"],
                    normalize_match_score_model(match.get("score_model")),
                    json.dumps(match.get("scoring_rule") or {}, ensure_ascii=False),
                    1 if match.get("exclude_from_team_scores") else 0,
                    match["played_on"],
                    match.get("group_label", ""),
                    match["table_label"],
                    match["format"],
                    match["duration_minutes"],
                    match["winning_camp"],
                    match.get("mvp_player_id", ""),
                    match.get("svp_player_id", ""),
                    match.get("scapegoat_player_id", ""),
                    match["notes"],
                ),
            )
            for sort_order, entry in enumerate(match["players"]):
                score_model = normalize_match_score_model(match.get("score_model"))
                score_breakdown = normalize_score_breakdown(entry)
                points_earned = (
                    calculate_score_breakdown_total(entry, match.get("scoring_rule"))
                    if uses_structured_score_model(score_model)
                    else float(entry.get("points_earned", 0.0))
                )
                connection.execute(
                    """
                    INSERT INTO match_players (
                        match_id, sort_order, player_id, team_id, seat, role, camp, survived, result,
                        points_earned, result_points, vote_points, behavior_points, special_points, adjustment_points,
                        score_breakdown_json, points_available, stance_pick, stance_correct, notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        match["match_id"],
                        sort_order,
                        entry["player_id"],
                        entry["team_id"],
                        entry["seat"],
                        entry["role"],
                        entry["camp"],
                        0,
                        entry["result"],
                        points_earned,
                        score_breakdown["result_points"],
                        score_breakdown["vote_points"],
                        score_breakdown["behavior_points"],
                        score_breakdown["special_points"],
                        score_breakdown["adjustment_points"],
                        json.dumps(score_breakdown, ensure_ascii=False),
                        float(entry.get("points_available", points_earned)),
                        to_legacy_stance_columns(
                            normalize_stance_result(entry),
                            match["winning_camp"],
                        )[0],
                        to_legacy_stance_columns(
                            normalize_stance_result(entry),
                            match["winning_camp"],
                        )[1],
                        entry["notes"],
                    ),
                )

        connection.execute(
            """
            INSERT INTO app_meta (meta_key, meta_value)
            VALUES ('initialized', '1')
            ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
            """
        )
        connection.execute(
            """
            INSERT INTO app_meta (meta_key, meta_value)
            VALUES (?, ?)
            ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
            """,
            (SCHEMA_VERSION_META_KEY, str(REQUIRED_SCHEMA_VERSION)),
        )
    if backend == "sqlite":
        connection.execute("PRAGMA foreign_keys = ON")


def ensure_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect_db() as connection:
        create_schema(connection)


def postgres_read_mode_enabled() -> bool:
    if (
        os.getenv("ENABLE_POSTGRES_READS", "").strip() != "1"
        and os.getenv("ENABLE_POSTGRES_WRITES", "").strip() != "1"
    ):
        return False
    from db_runtime import database_backend

    return database_backend() == "postgres"


def postgres_write_mode_enabled() -> bool:
    if os.getenv("ENABLE_POSTGRES_WRITES", "").strip() != "1":
        return False
    from db_runtime import database_backend

    return database_backend() == "postgres"


def connect_read_db() -> Any:
    if postgres_read_mode_enabled():
        from db_runtime import connect_runtime_db

        return connect_runtime_db()
    ensure_database()
    return connect_db()


def connect_write_db() -> Any:
    if postgres_write_mode_enabled():
        from db_runtime import connect_runtime_db

        return connect_runtime_db()
    ensure_database()
    return connect_db()


def require_initialized_database(connection: Any) -> None:
    if database_is_initialized(connection):
        return
    raise ValueError(
        "数据库尚未初始化。请先准备好 SQLite 主库，或完成 PostgreSQL 迁移后再使用。"
    )


def load_users(connection: Any | None = None) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        connection = connect_read_db()
    try:
        require_initialized_database(connection)
        rows = connection.execute(
            """
            SELECT username, display_name, password_salt, password_hash, active, player_id,
                   linked_player_ids_json, manager_scope_keys_json, permissions_json, role,
                   province_name, region_name, gender, bio, photo,
                   wechat_openid, wechat_web_openid, wechat_unionid
            FROM users
            ORDER BY username
            """
        ).fetchall()
        return [
            {
                "username": row["username"],
                "display_name": row["display_name"],
                "password_salt": row["password_salt"],
                "password_hash": row["password_hash"],
                "active": bool(row["active"]),
                "player_id": row["player_id"],
                "linked_player_ids": json.loads(row["linked_player_ids_json"] or "[]"),
                "manager_scope_keys": json.loads(row["manager_scope_keys_json"] or "[]"),
                "permissions": json.loads(row["permissions_json"] or "[]"),
                "role": row["role"] or ("admin" if row["username"] == "admin" else "member"),
                "province_name": row["province_name"] or "",
                "region_name": row["region_name"] or "",
                "gender": row["gender"] or "",
                "bio": row["bio"] or "",
                "photo": row["photo"] or DEFAULT_USER_PHOTO,
                "wechat_openid": row["wechat_openid"] or "",
                "wechat_web_openid": row["wechat_web_openid"] or "",
                "wechat_unionid": row["wechat_unionid"] or "",
            }
            for row in rows
        ]
    finally:
        if should_close:
            connection.close()


def upsert_users_only(connection: Any, users: list[dict[str, Any]]) -> None:
    incoming_usernames = {
        str(user.get("username") or "").strip()
        for user in users
        if str(user.get("username") or "").strip()
    }
    existing_rows = connection.execute("SELECT username FROM users").fetchall()
    for row in existing_rows:
        username = str(row["username"] or "").strip()
        if username and username not in incoming_usernames:
            connection.execute("DELETE FROM users WHERE username = ?", (username,))

    for user in users:
        username = str(user.get("username") or "").strip()
        if not username:
            continue
        connection.execute(
            """
            INSERT INTO users (
                username, display_name, password_salt, password_hash, active, player_id,
                linked_player_ids_json, manager_scope_keys_json, permissions_json, role,
                province_name, region_name, gender, bio, photo,
                wechat_openid, wechat_web_openid, wechat_unionid
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                display_name = excluded.display_name,
                password_salt = excluded.password_salt,
                password_hash = excluded.password_hash,
                active = excluded.active,
                player_id = excluded.player_id,
                linked_player_ids_json = excluded.linked_player_ids_json,
                manager_scope_keys_json = excluded.manager_scope_keys_json,
                permissions_json = excluded.permissions_json,
                role = excluded.role,
                province_name = excluded.province_name,
                region_name = excluded.region_name,
                gender = excluded.gender,
                bio = excluded.bio,
                photo = excluded.photo,
                wechat_openid = excluded.wechat_openid,
                wechat_web_openid = excluded.wechat_web_openid,
                wechat_unionid = excluded.wechat_unionid
            """,
            (
                username,
                user.get("display_name") or username,
                user["password_salt"],
                user["password_hash"],
                1 if user.get("active") else 0,
                user.get("player_id"),
                json.dumps(user.get("linked_player_ids", []), ensure_ascii=False),
                json.dumps(user.get("manager_scope_keys", []), ensure_ascii=False),
                json.dumps(user.get("permissions", []), ensure_ascii=False),
                user.get("role") or ("admin" if username == "admin" else "member"),
                user.get("province_name") or "",
                user.get("region_name") or "",
                user.get("gender") or "",
                user.get("bio") or "",
                user.get("photo") or DEFAULT_USER_PHOTO,
                user.get("wechat_openid") or "",
                user.get("wechat_web_openid") or "",
                user.get("wechat_unionid") or "",
            ),
        )


def save_users(users: list[dict[str, Any]]) -> None:
    if postgres_write_mode_enabled():
        with connect_write_db() as connection:
            require_initialized_database(connection)
            with connection.transaction():
                upsert_users_only(connection, users)
        return

    ensure_database()
    with connect_db() as connection:
        require_initialized_database(connection)
        guilds = load_guilds(connection)
        teams = load_teams(connection)
        players = load_players(connection)
        matches = load_matches(connection)
        replace_repository_data(
            connection,
            teams=teams,
            players=players,
            matches=matches,
            users=users,
            guilds=guilds,
        )


def load_guilds(connection: Any | None = None) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        connection = connect_read_db()
    try:
        require_initialized_database(connection)
        rows = connection.execute(
            """
            SELECT guild_id, name, short_name, logo, active, founded_on,
                   leader_username, manager_usernames_json, honors_json, notes
            FROM guilds
            ORDER BY guild_id
            """
        ).fetchall()
        return [
            {
                "guild_id": row["guild_id"],
                "name": row["name"],
                "short_name": row["short_name"],
                "logo": row["logo"],
                "active": bool(row["active"]),
                "founded_on": row["founded_on"],
                "leader_username": row["leader_username"],
                "manager_usernames": json.loads(row["manager_usernames_json"] or "[]"),
                "honors": json.loads(row["honors_json"] or "[]"),
                "notes": row["notes"],
            }
            for row in rows
        ]
    finally:
        if should_close:
            connection.close()


def load_teams(connection: Any | None = None) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        connection = connect_read_db()
    try:
        require_initialized_database(connection)
        team_rows = connection.execute(
            """
            SELECT team_id, name, short_name, logo, active, founded_on,
                   competition_name, season_name, guild_id, captain_player_id, stage_groups_json, notes
            FROM teams
            ORDER BY team_id
            """
        ).fetchall()
        member_rows = connection.execute(
            """
            SELECT team_id, player_id
            FROM team_members
            ORDER BY team_id, sort_order
            """
        ).fetchall()
        members_by_team: dict[str, list[str]] = {}
        for row in member_rows:
            members_by_team.setdefault(row["team_id"], []).append(row["player_id"])

        return [
            {
                "team_id": row["team_id"],
                "name": row["name"],
                "short_name": row["short_name"],
                "logo": row["logo"],
                "active": bool(row["active"]),
                "founded_on": row["founded_on"],
                "competition_name": row["competition_name"] or "",
                "season_name": row["season_name"] or "",
                "guild_id": row["guild_id"] or "",
                "captain_player_id": row["captain_player_id"] or None,
                "stage_groups": json.loads(row["stage_groups_json"] or "[]"),
                "members": members_by_team.get(row["team_id"], []),
                "notes": row["notes"],
            }
            for row in team_rows
        ]
    finally:
        if should_close:
            connection.close()


def load_players(connection: Any | None = None) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        connection = connect_read_db()
    try:
        require_initialized_database(connection)
        rows = connection.execute(
            """
            SELECT player_id, display_name, team_id, photo, aliases_json, active, joined_on, notes
            FROM players
            ORDER BY player_id
            """
        ).fetchall()
        return [
            {
                "player_id": row["player_id"],
                "display_name": row["display_name"],
                "team_id": row["team_id"],
                "photo": row["photo"],
                "aliases": json.loads(row["aliases_json"]),
                "active": bool(row["active"]),
                "joined_on": row["joined_on"],
                "notes": row["notes"],
            }
            for row in rows
        ]
    finally:
        if should_close:
            connection.close()


def load_matches(connection: Any | None = None) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        connection = connect_read_db()
    try:
        require_initialized_database(connection)
        match_rows = connection.execute(
            """
            SELECT match_id, competition_name, season, stage, round, game_no, score_model, scoring_rule_json, exclude_from_team_scores, played_on, group_label, table_label, format,
                   duration_minutes, winning_camp, mvp_player_id, svp_player_id, scapegoat_player_id, notes
            FROM matches
            ORDER BY played_on, round, game_no, match_id
            """
        ).fetchall()
        participant_rows = connection.execute(
            """
            SELECT match_id, player_id, team_id, seat, role, camp, survived, result,
                   points_earned, result_points, vote_points, behavior_points, special_points, adjustment_points,
                   score_breakdown_json, points_available, stance_pick, stance_correct, notes
            FROM match_players
            ORDER BY match_id, sort_order
            """
        ).fetchall()

        participants_by_match: dict[str, list[dict[str, Any]]] = {}
        for row in participant_rows:
            try:
                score_breakdown = json.loads(row["score_breakdown_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                score_breakdown = {}
            if not isinstance(score_breakdown, dict):
                score_breakdown = {}
            score_breakdown.update({
                field_name: float(row[field_name] or 0.0)
                for field_name in MATCH_SCORE_COMPONENT_FIELDS
            })
            participants_by_match.setdefault(row["match_id"], []).append(
                {
                    "player_id": row["player_id"],
                    "team_id": row["team_id"],
                    "seat": row["seat"],
                    "role": row["role"],
                    "camp": row["camp"],
                    "result": row["result"],
                    "points_earned": float(row["points_earned"]),
                    **{
                        field_name: score_breakdown.get(field_name, 0.0)
                        for field_name in MATCH_SCORE_COMPONENT_FIELDS
                    },
                    "score_breakdown": score_breakdown,
                    "stance_result": normalize_stance_result(
                        {
                            "stance_pick": row["stance_pick"],
                            "stance_correct": bool(row["stance_correct"]),
                        }
                    ),
                    "notes": row["notes"],
                }
            )

        return [
            {
                "match_id": row["match_id"],
                "competition_name": row["competition_name"] or row["season"],
                "season": row["season"],
                "stage": row["stage"],
                "round": row["round"],
                "game_no": row["game_no"],
                "score_model": normalize_match_score_model(row["score_model"]),
                "scoring_rule": json.loads(row["scoring_rule_json"] or "{}"),
                "exclude_from_team_scores": bool(row["exclude_from_team_scores"]),
                "played_on": row["played_on"],
                "group_label": row["group_label"] or "",
                "table_label": row["table_label"],
                "format": row["format"],
                "duration_minutes": row["duration_minutes"],
                "winning_camp": row["winning_camp"],
                "mvp_player_id": row["mvp_player_id"] or "",
                "svp_player_id": row["svp_player_id"] or "",
                "scapegoat_player_id": row["scapegoat_player_id"] or "",
                "players": participants_by_match.get(row["match_id"], []),
                "notes": row["notes"],
            }
            for row in match_rows
        ]
    finally:
        if should_close:
            connection.close()


def load_repository_data() -> dict[str, Any]:
    with connect_read_db() as connection:
        require_initialized_database(connection)
        return {
            "guilds": load_guilds(connection),
            "teams": load_teams(connection),
            "players": load_players(connection),
            "matches": load_matches(connection),
            "season_player_dimension_stats": load_season_player_dimension_stats(connection),
            "season_team_dimension_stats": load_season_team_dimension_stats(connection),
        }


def save_matches(matches: list[dict[str, Any]]) -> None:
    with connect_write_db() as connection:
        require_initialized_database(connection)
        guilds = load_guilds(connection)
        teams = load_teams(connection)
        players = load_players(connection)
        users = load_users(connection)
        replace_repository_data(
            connection,
            teams=teams,
            players=players,
            matches=matches,
            users=users,
            guilds=guilds,
        )


def save_repository_data(data: dict[str, Any], users: list[dict[str, Any]] | None = None) -> None:
    with connect_write_db() as connection:
        require_initialized_database(connection)
        replace_repository_data(
            connection,
            guilds=data.get("guilds", load_guilds(connection)),
            teams=data["teams"],
            players=data["players"],
            matches=data["matches"],
            users=users if users is not None else load_users(connection),
        )


def load_season_player_dimension_stats(
    connection: Any | None = None,
) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        connection = connect_read_db()
    try:
        require_initialized_database(connection)
        rows = connection.execute(
            """
            SELECT competition_name, season_name, played_on, player_id, team_id, seat, metrics_json
            FROM season_player_dimension_stats
            ORDER BY played_on, competition_name, season_name, seat, player_id
            """
        ).fetchall()
        return [
            {
                "competition_name": row["competition_name"],
                "season_name": row["season_name"],
                "played_on": row["played_on"],
                "player_id": row["player_id"],
                "team_id": row["team_id"],
                "seat": int(row["seat"] or 0),
                **json.loads(row["metrics_json"] or "{}"),
            }
            for row in rows
        ]
    finally:
        if should_close:
            connection.close()


def load_season_team_dimension_stats(
    connection: Any | None = None,
) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        connection = connect_read_db()
    try:
        require_initialized_database(connection)
        rows = connection.execute(
            """
            SELECT competition_name, season_name, played_on, team_id, seat, metrics_json
            FROM season_team_dimension_stats
            ORDER BY played_on, competition_name, season_name, seat, team_id
            """
        ).fetchall()
        return [
            {
                "competition_name": row["competition_name"],
                "season_name": row["season_name"],
                "played_on": row["played_on"],
                "team_id": row["team_id"],
                "seat": int(row["seat"] or 0),
                **json.loads(row["metrics_json"] or "{}"),
            }
            for row in rows
        ]
    finally:
        if should_close:
            connection.close()


def save_season_dimension_stats(
    player_rows: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
) -> None:
    with connect_write_db() as connection:
        require_initialized_database(connection)
        with transaction_context(connection):
            for row in player_rows:
                metrics = {
                    key: value
                    for key, value in row.items()
                    if key
                    not in {
                        "competition_name",
                        "season_name",
                        "played_on",
                        "player_id",
                        "team_id",
                        "seat",
                    }
                }
                connection.execute(
                    """
                    INSERT INTO season_player_dimension_stats (
                        competition_name, season_name, played_on, player_id, team_id, seat, metrics_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(competition_name, season_name, played_on, player_id)
                    DO UPDATE SET
                        team_id = excluded.team_id,
                        seat = excluded.seat,
                        metrics_json = excluded.metrics_json
                    """,
                    (
                        row["competition_name"],
                        row["season_name"],
                        row["played_on"],
                        row["player_id"],
                        row["team_id"],
                        int(row.get("seat") or 0),
                        json.dumps(metrics, ensure_ascii=False),
                    ),
                )
            for row in team_rows:
                metrics = {
                    key: value
                    for key, value in row.items()
                    if key
                    not in {
                        "competition_name",
                        "season_name",
                        "played_on",
                        "team_id",
                        "seat",
                    }
                }
                connection.execute(
                    """
                    INSERT INTO season_team_dimension_stats (
                        competition_name, season_name, played_on, team_id, seat, metrics_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(competition_name, season_name, played_on, team_id, seat)
                    DO UPDATE SET
                        metrics_json = excluded.metrics_json
                    """,
                    (
                        row["competition_name"],
                        row["season_name"],
                        row["played_on"],
                        row["team_id"],
                        int(row.get("seat") or 0),
                        json.dumps(metrics, ensure_ascii=False),
                    ),
                )


def clear_season_dimension_stats(
    competition_name: str,
    season_name: str,
) -> tuple[int, int]:
    with connect_write_db() as connection:
        require_initialized_database(connection)
        with transaction_context(connection):
            player_cursor = connection.execute(
                """
                DELETE FROM season_player_dimension_stats
                WHERE competition_name = ? AND season_name = ?
                """,
                (competition_name, season_name),
            )
            team_cursor = connection.execute(
                """
                DELETE FROM season_team_dimension_stats
                WHERE competition_name = ? AND season_name = ?
                """,
                (competition_name, season_name),
            )
        return int(player_cursor.rowcount or 0), int(team_cursor.rowcount or 0)


def clear_season_dimension_stats_for_day(
    competition_name: str,
    season_name: str,
    played_on: str,
) -> tuple[int, int]:
    with connect_write_db() as connection:
        require_initialized_database(connection)
        with transaction_context(connection):
            player_cursor = connection.execute(
                """
                DELETE FROM season_player_dimension_stats
                WHERE competition_name = ? AND season_name = ? AND played_on = ?
                """,
                (competition_name, season_name, played_on),
            )
            team_cursor = connection.execute(
                """
                DELETE FROM season_team_dimension_stats
                WHERE competition_name = ? AND season_name = ? AND played_on = ?
                """,
                (competition_name, season_name, played_on),
            )
        return int(player_cursor.rowcount or 0), int(team_cursor.rowcount or 0)


def load_membership_requests(connection: Any | None = None) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        connection = connect_read_db()
    try:
        require_initialized_database(connection)
        rows = connection.execute(
            """
            SELECT request_id, request_type, username, display_name, player_id,
                   source_team_id, target_team_id, target_guild_id,
                   scope_competition_name, scope_season_name, request_payload_json, created_on
            FROM membership_requests
            ORDER BY created_on, request_id
            """
        ).fetchall()
        return [
            {
                "request_id": row["request_id"],
                "request_type": row["request_type"],
                "username": row["username"],
                "display_name": row["display_name"],
                "player_id": row["player_id"],
                "source_team_id": row["source_team_id"],
                "target_team_id": row["target_team_id"],
                "target_guild_id": row["target_guild_id"] or "",
                "scope_competition_name": row["scope_competition_name"] or "",
                "scope_season_name": row["scope_season_name"] or "",
                "request_payload": json.loads(row["request_payload_json"] or "{}"),
                "created_on": row["created_on"],
            }
            for row in rows
        ]
    finally:
        if should_close:
            connection.close()


def save_membership_requests(requests: list[dict[str, Any]]) -> None:
    with connect_write_db() as connection:
        require_initialized_database(connection)
        with transaction_context(connection):
            connection.execute("DELETE FROM membership_requests")
            for item in requests:
                connection.execute(
                    """
                    INSERT INTO membership_requests (
                        request_id, request_type, username, display_name, player_id,
                        source_team_id, target_team_id, target_guild_id,
                        scope_competition_name, scope_season_name, request_payload_json, created_on
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["request_id"],
                        item["request_type"],
                        item["username"],
                        item["display_name"],
                        item.get("player_id"),
                        item.get("source_team_id"),
                        item.get("target_team_id", ""),
                        item.get("target_guild_id", ""),
                        item.get("scope_competition_name", ""),
                        item.get("scope_season_name", ""),
                        json.dumps(item.get("request_payload", {}), ensure_ascii=False),
                        item["created_on"],
                    ),
                )


def load_meta_value(
    meta_key: str,
    connection: Any | None = None,
) -> str | None:
    should_close = connection is None
    if connection is None:
        connection = connect_read_db()
    try:
        require_initialized_database(connection)
        row = connection.execute(
            "SELECT meta_value FROM app_meta WHERE meta_key = ?",
            (meta_key,),
        ).fetchone()
        if not row:
            return None
        return row["meta_value"]
    finally:
        if should_close:
            connection.close()


def save_meta_value(meta_key: str, meta_value: str) -> None:
    with connect_write_db() as connection:
        require_initialized_database(connection)
        connection.execute(
            """
            INSERT INTO app_meta (meta_key, meta_value)
            VALUES (?, ?)
            ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
            """,
            (meta_key, meta_value),
        )


def create_ai_job(
    *,
    job_type: str,
    scope_type: str = "",
    scope_key: str = "",
    model: str = "",
    created_by: str = "",
    created_at: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    job_id = "aijob_" + secrets.token_hex(12)
    with connect_write_db() as connection:
        require_initialized_database(connection)
        with transaction_context(connection):
            connection.execute(
                """
                INSERT INTO ai_jobs (
                    job_id, job_type, scope_type, scope_key, status, model,
                    created_by, created_at, updated_at, error_message, metadata_json
                )
                VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?, '', ?)
                """,
                (
                    job_id,
                    str(job_type or "").strip(),
                    str(scope_type or "").strip(),
                    str(scope_key or "").strip(),
                    str(model or "").strip(),
                    str(created_by or "").strip(),
                    created_at,
                    created_at,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
    return job_id


def update_ai_job_status(
    job_id: str,
    *,
    status: str,
    updated_at: str,
    model: str | None = None,
    error_message: str = "",
) -> None:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return
    with connect_write_db() as connection:
        require_initialized_database(connection)
        with transaction_context(connection):
            if model is None:
                connection.execute(
                    """
                    UPDATE ai_jobs
                    SET status = ?, updated_at = ?, error_message = ?
                    WHERE job_id = ?
                    """,
                    (
                        str(status or "").strip(),
                        updated_at,
                        str(error_message or "").strip(),
                        normalized_job_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE ai_jobs
                    SET status = ?, updated_at = ?, model = ?, error_message = ?
                    WHERE job_id = ?
                    """,
                    (
                        str(status or "").strip(),
                        updated_at,
                        str(model or "").strip(),
                        str(error_message or "").strip(),
                        normalized_job_id,
                    ),
                )


def add_ai_job_step(
    *,
    job_id: str,
    step_order: int,
    step_name: str,
    status: str,
    started_at: str,
    finished_at: str = "",
    input_summary: str = "",
    output_summary: str = "",
    error_message: str = "",
    metadata: dict[str, Any] | None = None,
) -> str:
    step_id = "aistep_" + secrets.token_hex(12)
    with connect_write_db() as connection:
        require_initialized_database(connection)
        with transaction_context(connection):
            connection.execute(
                """
                INSERT INTO ai_job_steps (
                    step_id, job_id, step_order, step_name, status, started_at,
                    finished_at, input_summary, output_summary, error_message,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step_id,
                    str(job_id or "").strip(),
                    int(step_order),
                    str(step_name or "").strip(),
                    str(status or "").strip(),
                    started_at,
                    str(finished_at or "").strip(),
                    str(input_summary or "").strip(),
                    str(output_summary or "").strip(),
                    str(error_message or "").strip(),
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
    return step_id


def load_ai_jobs(limit: int = 50) -> list[dict[str, Any]]:
    with connect_read_db() as connection:
        require_initialized_database(connection)
        job_rows = connection.execute(
            """
            SELECT job_id, job_type, scope_type, scope_key, status, model,
                   created_by, created_at, updated_at, error_message, metadata_json
            FROM ai_jobs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 200)),),
        ).fetchall()
        step_rows = connection.execute(
            """
            SELECT step_id, job_id, step_order, step_name, status, started_at,
                   finished_at, input_summary, output_summary, error_message,
                   metadata_json
            FROM ai_job_steps
            WHERE job_id IN (
                SELECT job_id FROM ai_jobs ORDER BY created_at DESC LIMIT ?
            )
            ORDER BY job_id, step_order
            """,
            (max(1, min(int(limit), 200)),),
        ).fetchall()

    steps_by_job: dict[str, list[dict[str, Any]]] = {}
    for row in step_rows:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        steps_by_job.setdefault(row["job_id"], []).append(
            {
                "step_id": row["step_id"],
                "job_id": row["job_id"],
                "step_order": row["step_order"],
                "step_name": row["step_name"],
                "status": row["status"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "input_summary": row["input_summary"],
                "output_summary": row["output_summary"],
                "error_message": row["error_message"],
                "metadata": metadata,
            }
        )

    jobs: list[dict[str, Any]] = []
    for row in job_rows:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        jobs.append(
            {
                "job_id": row["job_id"],
                "job_type": row["job_type"],
                "scope_type": row["scope_type"],
                "scope_key": row["scope_key"],
                "status": row["status"],
                "model": row["model"],
                "created_by": row["created_by"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "error_message": row["error_message"],
                "metadata": metadata,
                "steps": steps_by_job.get(row["job_id"], []),
            }
        )
    return jobs


def record_access_log(
    *,
    path: str,
    method: str,
    status_code: int = 0,
    duration_ms: int = 0,
    query_string: str = "",
    username: str = "",
    ip_address: str = "",
    user_agent: str = "",
    created_at: str,
    request_id: str = "",
) -> str:
    log_id = "access_" + secrets.token_hex(12)
    with connect_write_db() as connection:
        require_initialized_database(connection)
        with transaction_context(connection):
            connection.execute(
                """
                INSERT INTO access_logs (
                    log_id, request_id, path, method, status_code, duration_ms, query_string, username,
                    ip_address, user_agent, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    str(request_id or "").strip()[:80],
                    str(path or "").strip() or "/",
                    str(method or "").strip().upper() or "GET",
                    max(0, int(status_code or 0)),
                    max(0, int(duration_ms or 0)),
                    str(query_string or "").strip(),
                    str(username or "").strip(),
                    str(ip_address or "").strip(),
                    str(user_agent or "").strip()[:500],
                    created_at,
                ),
            )
    return log_id


def record_audit_log(
    *,
    action: str,
    target_type: str = "",
    target_id: str = "",
    summary: str = "",
    username: str = "",
    request_id: str = "",
    ip_address: str = "",
    created_at: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    audit_id = "audit_" + secrets.token_hex(12)
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
    with connect_write_db() as connection:
        require_initialized_database(connection)
        with transaction_context(connection):
            connection.execute(
                """
                INSERT INTO audit_logs (
                    audit_id, request_id, username, action, target_type, target_id,
                    summary, ip_address, created_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    str(request_id or "").strip()[:80],
                    str(username or "").strip()[:120],
                    str(action or "").strip()[:120],
                    str(target_type or "").strip()[:80],
                    str(target_id or "").strip()[:160],
                    str(summary or "").strip()[:1000],
                    str(ip_address or "").strip(),
                    created_at,
                    metadata_json,
                ),
            )
    return audit_id


def load_audit_logs(limit: int = 100) -> list[dict[str, Any]]:
    row_limit = max(1, min(int(limit), 500))
    with connect_read_db() as connection:
        require_initialized_database(connection)
        rows = connection.execute(
            """
            SELECT audit_id, request_id, username, action, target_type, target_id,
                   summary, ip_address, created_at, metadata_json
            FROM audit_logs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (row_limit,),
        ).fetchall()
    logs = []
    for row in rows:
        item = dict(row)
        try:
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["metadata"] = {}
        logs.append(item)
    return logs


def _decode_audit_row(row: Any) -> dict[str, Any]:
    item = dict(row)
    try:
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        item["metadata"] = {}
    return item


def load_request_trace(request_id: str) -> dict[str, Any]:
    normalized_request_id = str(request_id or "").strip()[:80]
    if not normalized_request_id:
        return {"request_id": "", "access_logs": [], "audit_logs": []}
    with connect_read_db() as connection:
        require_initialized_database(connection)
        access_rows = connection.execute(
            """
            SELECT log_id, request_id, path, method, status_code, duration_ms, query_string, username,
                   ip_address, user_agent, created_at
            FROM access_logs
            WHERE request_id = ?
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (normalized_request_id,),
        ).fetchall()
        audit_rows = connection.execute(
            """
            SELECT audit_id, request_id, username, action, target_type, target_id,
                   summary, ip_address, created_at, metadata_json
            FROM audit_logs
            WHERE request_id = ?
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (normalized_request_id,),
        ).fetchall()
    return {
        "request_id": normalized_request_id,
        "access_logs": [dict(row) for row in access_rows],
        "audit_logs": [_decode_audit_row(row) for row in audit_rows],
    }


def cleanup_expired_logs(
    *,
    access_retention_days: int = 30,
    audit_retention_days: int = 365,
    dry_run: bool = False,
) -> dict[str, Any]:
    access_days = max(1, int(access_retention_days or 30))
    audit_days = max(1, int(audit_retention_days or 365))
    access_cutoff_date = china_date_days_ago(access_days)
    audit_cutoff_date = china_date_days_ago(audit_days)
    with connect_write_db() as connection:
        require_initialized_database(connection)
        with transaction_context(connection):
            access_row = connection.execute(
                "SELECT COUNT(*) AS count FROM access_logs WHERE substr(created_at, 1, 10) < ?",
                (access_cutoff_date,),
            ).fetchone()
            audit_row = connection.execute(
                "SELECT COUNT(*) AS count FROM audit_logs WHERE substr(created_at, 1, 10) < ?",
                (audit_cutoff_date,),
            ).fetchone()
            deleted_access = int(access_row["count"] or 0)
            deleted_audit = int(audit_row["count"] or 0)
            if not dry_run:
                connection.execute(
                    "DELETE FROM access_logs WHERE substr(created_at, 1, 10) < ?",
                    (access_cutoff_date,),
                )
                connection.execute(
                    "DELETE FROM audit_logs WHERE substr(created_at, 1, 10) < ?",
                    (audit_cutoff_date,),
                )
                summary = {
                    "ran_at": datetime.now(timezone.utc)
                    .astimezone(timezone(timedelta(hours=8)))
                    .isoformat(timespec="seconds"),
                    "access_retention_days": access_days,
                    "audit_retention_days": audit_days,
                    "access_cutoff_date": access_cutoff_date,
                    "audit_cutoff_date": audit_cutoff_date,
                    "deleted_access_logs": deleted_access,
                    "deleted_audit_logs": deleted_audit,
                    "dry_run": False,
                }
                connection.execute(
                    """
                    INSERT INTO app_meta (meta_key, meta_value)
                    VALUES (?, ?)
                    ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
                    """,
                    (LOG_CLEANUP_META_KEY, json.dumps(summary, ensure_ascii=False, sort_keys=True)),
                )
    return {
        "access_retention_days": access_days,
        "audit_retention_days": audit_days,
        "access_cutoff_date": access_cutoff_date,
        "audit_cutoff_date": audit_cutoff_date,
        "deleted_access_logs": deleted_access,
        "deleted_audit_logs": deleted_audit,
        "dry_run": bool(dry_run),
    }


def load_log_cleanup_state() -> dict[str, Any]:
    raw_value = load_meta_value(LOG_CLEANUP_META_KEY)
    if not raw_value:
        return {}
    try:
        state = json.loads(raw_value)
    except json.JSONDecodeError:
        return {"raw": raw_value}
    return state if isinstance(state, dict) else {"raw": raw_value}


def load_access_overview(limit: int = 80) -> dict[str, Any]:
    row_limit = max(1, min(int(limit), 300))
    with connect_read_db() as connection:
        require_initialized_database(connection)
        total_row = connection.execute("SELECT COUNT(*) AS count FROM access_logs").fetchone()
        today_row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM access_logs
            WHERE substr(created_at, 1, 10) = ?
            """,
            (china_today_iso(),),
        ).fetchone()
        unique_ip_row = connection.execute(
            "SELECT COUNT(DISTINCT ip_address) AS count FROM access_logs WHERE ip_address != ''"
        ).fetchone()
        error_row = connection.execute(
            "SELECT COUNT(*) AS count FROM access_logs WHERE status_code >= 400"
        ).fetchone()
        slow_row = connection.execute(
            "SELECT COUNT(*) AS count FROM access_logs WHERE duration_ms >= 1000"
        ).fetchone()
        duration_row = connection.execute(
            """
            SELECT AVG(duration_ms) AS avg_duration_ms, MAX(duration_ms) AS max_duration_ms
            FROM access_logs
            WHERE duration_ms > 0
            """
        ).fetchone()
        status_rows = connection.execute(
            """
            SELECT status_code, COUNT(*) AS count
            FROM access_logs
            GROUP BY status_code
            ORDER BY count DESC, status_code ASC
            LIMIT 10
            """
        ).fetchall()
        top_path_rows = connection.execute(
            """
            SELECT path, COUNT(*) AS visits, MAX(created_at) AS last_seen_at
            FROM access_logs
            GROUP BY path
            ORDER BY visits DESC, last_seen_at DESC
            LIMIT 10
            """
        ).fetchall()
        recent_rows = connection.execute(
            """
            SELECT log_id, request_id, path, method, status_code, duration_ms, query_string, username, ip_address,
                   user_agent, created_at
            FROM access_logs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (row_limit,),
        ).fetchall()
        slow_rows = connection.execute(
            """
            SELECT log_id, request_id, path, method, status_code, duration_ms, query_string, username,
                   ip_address, user_agent, created_at
            FROM access_logs
            WHERE duration_ms > 0
            ORDER BY duration_ms DESC, created_at DESC
            LIMIT 10
            """
        ).fetchall()
        error_rows = connection.execute(
            """
            SELECT log_id, request_id, path, method, status_code, duration_ms, query_string, username,
                   ip_address, user_agent, created_at
            FROM access_logs
            WHERE status_code >= 400
            ORDER BY created_at DESC
            LIMIT 10
            """
        ).fetchall()
    return {
        "total_visits": int(total_row["count"] or 0),
        "today_visits": int(today_row["count"] or 0),
        "unique_ip_count": int(unique_ip_row["count"] or 0),
        "error_count": int(error_row["count"] or 0),
        "slow_count": int(slow_row["count"] or 0),
        "avg_duration_ms": int(float(duration_row["avg_duration_ms"] or 0)),
        "max_duration_ms": int(duration_row["max_duration_ms"] or 0),
        "status_counts": [dict(row) for row in status_rows],
        "top_paths": [dict(row) for row in top_path_rows],
        "slow_logs": [dict(row) for row in slow_rows],
        "error_logs": [dict(row) for row in error_rows],
        "recent_logs": [dict(row) for row in recent_rows],
    }


def load_operational_overview(limit: int = 80) -> dict[str, Any]:
    row_limit = max(1, min(int(limit), 300))
    with connect_read_db() as connection:
        require_initialized_database(connection)
        api_total_row = connection.execute(
            "SELECT COUNT(*) AS count FROM access_logs WHERE path LIKE '/api/%'"
        ).fetchone()
        api_today_row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM access_logs
            WHERE path LIKE '/api/%' AND substr(created_at, 1, 10) = ?
            """,
            (china_today_iso(),),
        ).fetchone()
        api_error_row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM access_logs
            WHERE path LIKE '/api/%' AND status_code >= 400
            """
        ).fetchone()
        api_slow_row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM access_logs
            WHERE path LIKE '/api/%' AND duration_ms >= 1000
            """
        ).fetchone()
        api_duration_row = connection.execute(
            """
            SELECT AVG(duration_ms) AS avg_duration_ms, MAX(duration_ms) AS max_duration_ms
            FROM access_logs
            WHERE path LIKE '/api/%' AND duration_ms > 0
            """
        ).fetchone()
        api_path_rows = connection.execute(
            """
            SELECT
                path,
                COUNT(*) AS visits,
                AVG(duration_ms) AS avg_duration_ms,
                MAX(duration_ms) AS max_duration_ms,
                SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_count,
                SUM(CASE WHEN duration_ms >= 1000 THEN 1 ELSE 0 END) AS slow_count,
                MAX(created_at) AS last_seen_at
            FROM access_logs
            WHERE path LIKE '/api/%'
            GROUP BY path
            ORDER BY max_duration_ms DESC, visits DESC
            LIMIT 12
            """
        ).fetchall()
        recent_api_rows = connection.execute(
            """
            SELECT log_id, request_id, path, method, status_code, duration_ms, query_string, username,
                   ip_address, user_agent, created_at
            FROM access_logs
            WHERE path LIKE '/api/%'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (row_limit,),
        ).fetchall()
        recent_problem_rows = connection.execute(
            """
            SELECT log_id, request_id, path, method, status_code, duration_ms, query_string, username,
                   ip_address, user_agent, created_at
            FROM access_logs
            WHERE path LIKE '/api/%' AND (status_code >= 400 OR duration_ms >= 1000)
            ORDER BY created_at DESC
            LIMIT 20
            """
        ).fetchall()
    return {
        "api_total": int(api_total_row["count"] or 0),
        "api_today": int(api_today_row["count"] or 0),
        "api_error_count": int(api_error_row["count"] or 0),
        "api_slow_count": int(api_slow_row["count"] or 0),
        "api_avg_duration_ms": int(float(api_duration_row["avg_duration_ms"] or 0)),
        "api_max_duration_ms": int(api_duration_row["max_duration_ms"] or 0),
        "api_paths": [dict(row) for row in api_path_rows],
        "recent_api_logs": [dict(row) for row in recent_api_rows],
        "recent_problem_logs": [dict(row) for row in recent_problem_rows],
    }


def record_ai_conversation(
    *,
    competition_name: str = "",
    season_name: str = "",
    region_name: str = "",
    series_slug: str = "",
    question: str,
    answer: str,
    model: str = "",
    username: str = "",
    created_at: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    conversation_id = "aichat_" + secrets.token_hex(12)
    with connect_write_db() as connection:
        require_initialized_database(connection)
        with transaction_context(connection):
            connection.execute(
                """
                INSERT INTO ai_conversations (
                    conversation_id, competition_name, season_name, region_name,
                    series_slug, question, answer, model, username, created_at,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    str(competition_name or "").strip(),
                    str(season_name or "").strip(),
                    str(region_name or "").strip(),
                    str(series_slug or "").strip(),
                    str(question or "").strip(),
                    str(answer or "").strip(),
                    str(model or "").strip(),
                    str(username or "").strip(),
                    created_at,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
    return conversation_id


def load_ai_conversations(limit: int = 80) -> list[dict[str, Any]]:
    with connect_read_db() as connection:
        require_initialized_database(connection)
        rows = connection.execute(
            """
            SELECT conversation_id, competition_name, season_name, region_name,
                   series_slug, question, answer, model, username, created_at,
                   metadata_json
            FROM ai_conversations
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 300)),),
        ).fetchall()
    conversations: list[dict[str, Any]] = []
    for row in rows:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        item = dict(row)
        item["metadata"] = metadata
        item.pop("metadata_json", None)
        conversations.append(item)
    return conversations


def load_session_username(session_token: str) -> str | None:
    normalized_token = str(session_token or "").strip()
    if not normalized_token:
        return None
    with connect_read_db() as connection:
        require_initialized_database(connection)
        row = connection.execute(
            """
            SELECT username
            FROM user_sessions
            WHERE session_token = ?
            """,
            (normalized_token,),
        ).fetchone()
        if not row:
            return None
        return str(row["username"] or "").strip() or None


def save_session(session_token: str, username: str) -> None:
    normalized_token = str(session_token or "").strip()
    normalized_username = str(username or "").strip()
    if not normalized_token or not normalized_username:
        return
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect_write_db() as connection:
        require_initialized_database(connection)
        connection.execute(
            """
            INSERT INTO user_sessions (session_token, username, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(session_token) DO UPDATE SET
                username = excluded.username,
                created_at = excluded.created_at
            """,
            (normalized_token, normalized_username, created_at),
        )


def delete_session(session_token: str) -> None:
    normalized_token = str(session_token or "").strip()
    if not normalized_token:
        return
    with connect_write_db() as connection:
        require_initialized_database(connection)
        connection.execute(
            "DELETE FROM user_sessions WHERE session_token = ?",
            (normalized_token,),
        )


def delete_sessions_for_username(username: str) -> None:
    normalized_username = str(username or "").strip()
    if not normalized_username:
        return
    with connect_write_db() as connection:
        require_initialized_database(connection)
        connection.execute(
            "DELETE FROM user_sessions WHERE username = ?",
            (normalized_username,),
        )
