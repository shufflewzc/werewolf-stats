#!/usr/bin/env python3

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "werewolf_stats.db"


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
            player_id TEXT UNIQUE
        );

        CREATE TABLE IF NOT EXISTS app_meta (
            meta_key TEXT PRIMARY KEY,
            meta_value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS teams (
            team_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            short_name TEXT NOT NULL,
            logo TEXT NOT NULL,
            active INTEGER NOT NULL CHECK (active IN (0, 1)),
            founded_on TEXT NOT NULL,
            captain_player_id TEXT,
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
            played_on TEXT NOT NULL,
            table_label TEXT NOT NULL,
            format TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            winning_camp TEXT NOT NULL,
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

        CREATE TABLE IF NOT EXISTS membership_requests (
            request_id TEXT PRIMARY KEY,
            request_type TEXT NOT NULL,
            username TEXT NOT NULL,
            display_name TEXT NOT NULL,
            player_id TEXT,
            source_team_id TEXT,
            target_team_id TEXT NOT NULL,
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
    team_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(teams)").fetchall()
    }
    if "captain_player_id" not in team_columns:
        connection.execute("ALTER TABLE teams ADD COLUMN captain_player_id TEXT")
    match_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(matches)").fetchall()
    }
    if "competition_name" not in match_columns:
        connection.execute("ALTER TABLE matches ADD COLUMN competition_name TEXT")
        connection.execute(
            "UPDATE matches SET competition_name = season WHERE competition_name IS NULL OR competition_name = ''"
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
) -> None:
    with connection:
        connection.execute("DELETE FROM match_players")
        connection.execute("DELETE FROM matches")
        connection.execute("DELETE FROM team_members")
        connection.execute("DELETE FROM players")
        connection.execute("DELETE FROM teams")
        connection.execute("DELETE FROM users")

        for user in users:
            connection.execute(
                """
                INSERT INTO users (username, display_name, password_salt, password_hash, active, player_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user["username"],
                    user.get("display_name") or user["username"],
                    user["password_salt"],
                    user["password_hash"],
                    1 if user.get("active") else 0,
                    user.get("player_id"),
                ),
            )

        for team in teams:
            captain_player_id = team.get("captain_player_id")
            if not captain_player_id and team["members"]:
                captain_player_id = team["members"][0]
            connection.execute(
                """
                INSERT INTO teams (team_id, name, short_name, logo, active, founded_on, captain_player_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    team["team_id"],
                    team["name"],
                    team["short_name"],
                    team["logo"],
                    1 if team.get("active") else 0,
                    team["founded_on"],
                    captain_player_id,
                    team["notes"],
                ),
            )
            for sort_order, player_id in enumerate(team["members"]):
                connection.execute(
                    """
                    INSERT INTO team_members (team_id, player_id, sort_order)
                    VALUES (?, ?, ?)
                    """,
                    (team["team_id"], player_id, sort_order),
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

        for match in matches:
            connection.execute(
                """
                INSERT INTO matches (
                    match_id, competition_name, season, stage, round, game_no, played_on, table_label, format,
                    duration_minutes, winning_camp, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match["match_id"],
                    match.get("competition_name") or match["season"],
                    match["season"],
                    match["stage"],
                    match["round"],
                    match["game_no"],
                    match["played_on"],
                    match["table_label"],
                    match["format"],
                    match["duration_minutes"],
                    match["winning_camp"],
                    match["notes"],
                ),
            )
            for sort_order, entry in enumerate(match["players"]):
                connection.execute(
                    """
                    INSERT INTO match_players (
                        match_id, sort_order, player_id, team_id, seat, role, camp, survived, result,
                        points_earned, points_available, stance_pick, stance_correct, notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        match["match_id"],
                        sort_order,
                        entry["player_id"],
                        entry["team_id"],
                        entry["seat"],
                        entry["role"],
                        entry["camp"],
                        1 if entry.get("survived") else 0,
                        entry["result"],
                        float(entry["points_earned"]),
                        float(entry["points_available"]),
                        entry["stance_pick"],
                        1 if entry.get("stance_correct") else 0,
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
            SELECT username, display_name, password_salt, password_hash, active, player_id
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
        teams = load_teams(connection)
        players = load_players(connection)
        matches = load_matches(connection)
        replace_repository_data(connection, teams=teams, players=players, matches=matches, users=users)


def load_teams(connection: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    should_close = connection is None
    if connection is None:
        ensure_database()
        connection = connect_db()
    try:
        require_initialized_database(connection)
        team_rows = connection.execute(
            """
            SELECT team_id, name, short_name, logo, active, founded_on, captain_player_id, notes
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
                "captain_player_id": row["captain_player_id"] or (members_by_team.get(row["team_id"], [None])[0]),
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
            SELECT match_id, competition_name, season, stage, round, game_no, played_on, table_label, format,
                   duration_minutes, winning_camp, notes
            FROM matches
            ORDER BY played_on, round, game_no, match_id
            """
        ).fetchall()
        participant_rows = connection.execute(
            """
            SELECT match_id, player_id, team_id, seat, role, camp, survived, result,
                   points_earned, points_available, stance_pick, stance_correct, notes
            FROM match_players
            ORDER BY match_id, sort_order
            """
        ).fetchall()

        participants_by_match: dict[str, list[dict[str, Any]]] = {}
        for row in participant_rows:
            participants_by_match.setdefault(row["match_id"], []).append(
                {
                    "player_id": row["player_id"],
                    "team_id": row["team_id"],
                    "seat": row["seat"],
                    "role": row["role"],
                    "camp": row["camp"],
                    "survived": bool(row["survived"]),
                    "result": row["result"],
                    "points_earned": float(row["points_earned"]),
                    "points_available": float(row["points_available"]),
                    "stance_pick": row["stance_pick"],
                    "stance_correct": bool(row["stance_correct"]),
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
                "played_on": row["played_on"],
                "table_label": row["table_label"],
                "format": row["format"],
                "duration_minutes": row["duration_minutes"],
                "winning_camp": row["winning_camp"],
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
            "teams": load_teams(connection),
            "players": load_players(connection),
            "matches": load_matches(connection),
        }


def save_matches(matches: list[dict[str, Any]]) -> None:
    ensure_database()
    with connect_db() as connection:
        require_initialized_database(connection)
        teams = load_teams(connection)
        players = load_players(connection)
        users = load_users(connection)
        replace_repository_data(connection, teams=teams, players=players, matches=matches, users=users)


def save_repository_data(data: dict[str, Any], users: list[dict[str, Any]] | None = None) -> None:
    ensure_database()
    with connect_db() as connection:
        require_initialized_database(connection)
        replace_repository_data(
            connection,
            teams=data["teams"],
            players=data["players"],
            matches=data["matches"],
            users=users if users is not None else load_users(connection),
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
                   source_team_id, target_team_id, created_on
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
                        source_team_id, target_team_id, created_on
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["request_id"],
                        item["request_type"],
                        item["username"],
                        item["display_name"],
                        item.get("player_id"),
                        item.get("source_team_id"),
                        item["target_team_id"],
                        item["created_on"],
                    ),
                )
