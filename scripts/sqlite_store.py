#!/usr/bin/env python3

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from web_authz import DEFAULT_EVENT_MANAGER_PERMISSION_KEYS


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "werewolf_stats.db"
DEFAULT_USER_PHOTO = "assets/players/default-player.svg"


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
    return {
        field_name: float(entry.get(field_name, 0.0) or 0.0)
        for field_name in MATCH_SCORE_COMPONENT_FIELDS
    }


def calculate_score_breakdown_total(entry: dict[str, Any]) -> float:
    return round(sum(normalize_score_breakdown(entry).values()), 2)


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
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
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
            photo TEXT NOT NULL DEFAULT 'assets/players/default-player.svg'
        );

        CREATE TABLE IF NOT EXISTS app_meta (
            meta_key TEXT PRIMARY KEY,
            meta_value TEXT NOT NULL
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
    match_player_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(match_players)").fetchall()
    }
    for column_name in MATCH_SCORE_COMPONENT_FIELDS:
        if column_name not in match_player_columns:
            connection.execute(
                f"ALTER TABLE match_players ADD COLUMN {column_name} REAL NOT NULL DEFAULT 0"
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


def database_is_initialized(connection: sqlite3.Connection) -> bool:
    cursor = connection.execute(
        "SELECT meta_value FROM app_meta WHERE meta_key = 'initialized'"
    )
    row = cursor.fetchone()
    return bool(row and row["meta_value"] == "1")


def replace_repository_data(
    connection: sqlite3.Connection,
    teams: list[dict[str, Any]],
    players: list[dict[str, Any]],
    matches: list[dict[str, Any]],
    users: list[dict[str, Any]],
    guilds: list[dict[str, Any]] | None = None,
) -> None:
    guild_rows = guilds or []
    with connection:
        connection.execute("DELETE FROM match_players")
        connection.execute("DELETE FROM matches")
        connection.execute("DELETE FROM team_members")
        connection.execute("DELETE FROM players")
        connection.execute("DELETE FROM teams")
        connection.execute("DELETE FROM guilds")
        connection.execute("DELETE FROM users")

        for user in users:
            connection.execute(
                """
                INSERT INTO users (
                    username, display_name, password_salt, password_hash, active, player_id,
                    linked_player_ids_json, manager_scope_keys_json, permissions_json, role,
                    province_name, region_name, gender, bio, photo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    match_id, competition_name, season, stage, round, game_no, score_model, played_on, group_label, table_label, format,
                    duration_minutes, winning_camp, mvp_player_id, svp_player_id, scapegoat_player_id, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match["match_id"],
                    match.get("competition_name") or match["season"],
                    match["season"],
                    match["stage"],
                    match["round"],
                    match["game_no"],
                    normalize_match_score_model(match.get("score_model")),
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
                    calculate_score_breakdown_total(entry)
                    if uses_structured_score_model(score_model)
                    else float(entry.get("points_earned", 0.0))
                )
                connection.execute(
                    """
                    INSERT INTO match_players (
                        match_id, sort_order, player_id, team_id, seat, role, camp, survived, result,
                        points_earned, result_points, vote_points, behavior_points, special_points, adjustment_points,
                        points_available, stance_pick, stance_correct, notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def ensure_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect_db() as connection:
        create_schema(connection)


def require_initialized_database(connection: sqlite3.Connection) -> None:
    if database_is_initialized(connection):
        return
    raise ValueError(
        "SQLite 数据库尚未初始化。请先运行 `python3 scripts/migrate_json_to_sqlite.py`，"
        "或准备好 `data/werewolf_stats.db` 后再使用。"
    )


def load_users(connection: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        ensure_database()
        connection = connect_db()
    try:
        require_initialized_database(connection)
        rows = connection.execute(
            """
            SELECT username, display_name, password_salt, password_hash, active, player_id,
                   linked_player_ids_json, manager_scope_keys_json, permissions_json, role,
                   province_name, region_name, gender, bio, photo
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
            }
            for row in rows
        ]
    finally:
        if should_close:
            connection.close()


def save_users(users: list[dict[str, Any]]) -> None:
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


def load_guilds(connection: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        ensure_database()
        connection = connect_db()
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


def load_teams(connection: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        ensure_database()
        connection = connect_db()
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


def load_players(connection: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        ensure_database()
        connection = connect_db()
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


def load_matches(connection: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        ensure_database()
        connection = connect_db()
    try:
        require_initialized_database(connection)
        match_rows = connection.execute(
            """
            SELECT match_id, competition_name, season, stage, round, game_no, score_model, played_on, group_label, table_label, format,
                   duration_minutes, winning_camp, mvp_player_id, svp_player_id, scapegoat_player_id, notes
            FROM matches
            ORDER BY played_on, round, game_no, match_id
            """
        ).fetchall()
        participant_rows = connection.execute(
            """
            SELECT match_id, player_id, team_id, seat, role, camp, survived, result,
                   points_earned, result_points, vote_points, behavior_points, special_points, adjustment_points,
                   points_available, stance_pick, stance_correct, notes
            FROM match_players
            ORDER BY match_id, sort_order
            """
        ).fetchall()

        participants_by_match: dict[str, list[dict[str, Any]]] = {}
        for row in participant_rows:
            score_breakdown = {
                field_name: float(row[field_name] or 0.0)
                for field_name in MATCH_SCORE_COMPONENT_FIELDS
            }
            participants_by_match.setdefault(row["match_id"], []).append(
                {
                    "player_id": row["player_id"],
                    "team_id": row["team_id"],
                    "seat": row["seat"],
                    "role": row["role"],
                    "camp": row["camp"],
                    "result": row["result"],
                    "points_earned": float(row["points_earned"]),
                    **score_breakdown,
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
    ensure_database()
    with connect_db() as connection:
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
    ensure_database()
    with connect_db() as connection:
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
    ensure_database()
    with connect_db() as connection:
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
    connection: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        ensure_database()
        connection = connect_db()
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
    connection: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        ensure_database()
        connection = connect_db()
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
    ensure_database()
    with connect_db() as connection:
        require_initialized_database(connection)
        with connection:
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


def load_membership_requests(connection: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        ensure_database()
        connection = connect_db()
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
    ensure_database()
    with connect_db() as connection:
        require_initialized_database(connection)
        with connection:
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
    connection: sqlite3.Connection | None = None,
) -> str | None:
    should_close = connection is None
    if connection is None:
        ensure_database()
        connection = connect_db()
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
    ensure_database()
    with connect_db() as connection:
        require_initialized_database(connection)
        with connection:
            connection.execute(
                """
                INSERT INTO app_meta (meta_key, meta_value)
                VALUES (?, ?)
                ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
                """,
                (meta_key, meta_value),
            )


def load_session_username(session_token: str) -> str | None:
    normalized_token = str(session_token or "").strip()
    if not normalized_token:
        return None
    ensure_database()
    with connect_db() as connection:
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
    ensure_database()
    with connect_db() as connection:
        require_initialized_database(connection)
        with connection:
            connection.execute(
                """
                INSERT INTO user_sessions (session_token, username)
                VALUES (?, ?)
                ON CONFLICT(session_token) DO UPDATE SET
                    username = excluded.username,
                    created_at = CURRENT_TIMESTAMP
                """,
                (normalized_token, normalized_username),
            )


def delete_session(session_token: str) -> None:
    normalized_token = str(session_token or "").strip()
    if not normalized_token:
        return
    ensure_database()
    with connect_db() as connection:
        require_initialized_database(connection)
        with connection:
            connection.execute(
                "DELETE FROM user_sessions WHERE session_token = ?",
                (normalized_token,),
            )


def delete_sessions_for_username(username: str) -> None:
    normalized_username = str(username or "").strip()
    if not normalized_username:
        return
    ensure_database()
    with connect_db() as connection:
        require_initialized_database(connection)
        with connection:
            connection.execute(
                "DELETE FROM user_sessions WHERE username = ?",
                (normalized_username,),
            )
