#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, unquote, urlparse


MANIFEST_VERSION = 1
DATA_REVISION_KEY = "repository"
PLAYER_COLUMNS = (
    "competition_name",
    "season_name",
    "played_on",
    "player_id",
    "team_id",
    "seat",
    "metrics_json",
)
TEAM_COLUMNS = (
    "competition_name",
    "season_name",
    "played_on",
    "team_id",
    "seat",
    "metrics_json",
)
PLAYER_KEY_COLUMNS = ("competition_name", "season_name", "played_on", "player_id")
TEAM_KEY_COLUMNS = ("competition_name", "season_name", "played_on", "team_id", "seat")
REQUIRED_BACKUP_TABLES = (
    "audit_logs",
    "data_revisions",
    "matches",
    "match_players",
    "players",
    "teams",
    "season_player_dimension_stats",
    "season_team_dimension_stats",
)


class MigrationError(RuntimeError):
    pass


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export and safely import one season's dimension rows."
    )
    parser.add_argument("--competition", required=True)
    parser.add_argument("--season", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sqlite-db", type=Path)
    source.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--write-manifest",
        type=Path,
        help="Export the selected SQLite rows to a scoped JSON manifest and exit.",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="Target PostgreSQL URL. Defaults to DATABASE_URL.",
    )
    parser.add_argument("--expect-player-rows", type=int, required=True)
    parser.add_argument("--expect-team-rows", type=int, required=True)
    parser.add_argument("--expect-target-player-rows", type=int, default=0)
    parser.add_argument("--expect-target-team-rows", type=int, default=0)
    parser.add_argument(
        "--map-player-id",
        action="append",
        default=[],
        metavar="OLD=NEW",
        help=(
            "Explicitly map a legacy player ID to the proven target ID. "
            "May be repeated; every mapping must be used."
        ),
    )
    parser.add_argument(
        "--expect-data-revision",
        type=int,
        help="Required with --apply; protects against concurrent production writes.",
    )
    parser.add_argument(
        "--backup-reference",
        default="",
        help=(
            "Required with --apply; absolute destination for a new full pg_dump. "
            "The path must not already exist."
        ),
    )
    parser.add_argument(
        "--create-backup",
        action="store_true",
        help=(
            "Required with --apply; create the backup from the same DATABASE_URL "
            "before opening the migration transaction."
        ),
    )
    parser.add_argument(
        "--expect-manifest-sha256",
        default="",
        help=(
            "Approved manifest content SHA-256. Required with --apply and checked "
            "against the embedded source revision and rows."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write after all preconditions pass. Without this flag the target is read-only.",
    )
    return parser.parse_args(argv)


def normalized_row(row: Any, columns: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise MigrationError("dimension row must be a JSON object")
    normalized = {column: row.get(column) for column in columns}
    for column in columns:
        if normalized[column] is None:
            raise MigrationError(f"row has null {column}: {row}")
    try:
        normalized["seat"] = int(normalized["seat"])
    except (TypeError, ValueError) as exc:
        raise MigrationError(f"row has invalid seat: {row}") from exc
    normalized["metrics_json"] = str(normalized["metrics_json"])
    try:
        metrics = json.loads(normalized["metrics_json"])
    except json.JSONDecodeError as exc:
        raise MigrationError(f"invalid metrics_json: {exc}") from exc
    if not isinstance(metrics, dict):
        raise MigrationError("metrics_json must contain a JSON object")
    for key in ("daily_points", "games_played"):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MigrationError(f"metrics_json has invalid {key}: {row}")
    if float(metrics["games_played"]) < 0 or not float(
        metrics["games_played"]
    ).is_integer():
        raise MigrationError(f"metrics_json has invalid games_played: {row}")
    for column in columns:
        if column not in {"seat", "metrics_json"}:
            normalized[column] = str(normalized[column]).strip()
            if not normalized[column] and column != "team_id":
                raise MigrationError(f"row has empty {column}: {row}")
    return normalized


def validate_rows(
    rows: Iterable[dict[str, Any]],
    *,
    columns: tuple[str, ...],
    key_columns: tuple[str, ...],
    competition: str,
    season: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_keys: set[tuple[Any, ...]] = set()
    for source_row in rows:
        row = normalized_row(source_row, columns)
        if row["competition_name"] != competition or row["season_name"] != season:
            raise MigrationError(
                "manifest contains another scope: "
                f"{row['competition_name']} / {row['season_name']}"
            )
        key = tuple(row[column] for column in key_columns)
        if key in seen_keys:
            raise MigrationError(f"duplicate source key: {key}")
        seen_keys.add(key)
        normalized.append(row)
    normalized.sort(key=lambda row: tuple(row[column] for column in key_columns))
    return normalized


def payload_digest(player_rows: list[dict[str, Any]], team_rows: list[dict[str, Any]]) -> str:
    payload = {"player_rows": player_rows, "team_rows": team_rows}
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def manifest_digest(
    competition: str,
    season: str,
    source_data_revision: int,
    player_rows: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
) -> str:
    payload = {
        "competition": competition,
        "season": season,
        "source_data_revision": source_data_revision,
        "player_rows": player_rows,
        "team_rows": team_rows,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_sqlite_rows(
    path: Path,
    competition: str,
    season: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    if not path.is_file():
        raise MigrationError(f"SQLite database does not exist: {path}")
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        revision_row = connection.execute(
            "SELECT revision FROM data_revisions WHERE revision_key = ?",
            (DATA_REVISION_KEY,),
        ).fetchone()
        if not revision_row:
            raise MigrationError("source database has no repository data revision")
        source_data_revision = int(revision_row["revision"] or 0)
        player_rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT competition_name, season_name, played_on, player_id,
                       team_id, seat, metrics_json
                FROM season_player_dimension_stats
                WHERE competition_name = ? AND season_name = ?
                ORDER BY played_on, player_id
                """,
                (competition, season),
            ).fetchall()
        ]
        team_rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT competition_name, season_name, played_on, team_id,
                       seat, metrics_json
                FROM season_team_dimension_stats
                WHERE competition_name = ? AND season_name = ?
                ORDER BY played_on, team_id, seat
                """,
                (competition, season),
            ).fetchall()
        ]
        connection.commit()
    finally:
        connection.close()
    return player_rows, team_rows, source_data_revision


def build_manifest(
    competition: str,
    season: str,
    source_data_revision: int,
    player_rows: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    validated_players = validate_rows(
        player_rows,
        columns=PLAYER_COLUMNS,
        key_columns=PLAYER_KEY_COLUMNS,
        competition=competition,
        season=season,
    )
    validated_teams = validate_rows(
        team_rows,
        columns=TEAM_COLUMNS,
        key_columns=TEAM_KEY_COLUMNS,
        competition=competition,
        season=season,
    )
    return {
        "manifest_version": MANIFEST_VERSION,
        "competition": competition,
        "season": season,
        "source_data_revision": int(source_data_revision),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "player_rows": validated_players,
        "team_rows": validated_teams,
        "sha256": manifest_digest(
            competition,
            season,
            int(source_data_revision),
            validated_players,
            validated_teams,
        ),
    }


def validate_manifest(
    manifest: Any, competition: str, season: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    if not isinstance(manifest, dict):
        raise MigrationError("manifest root must be a JSON object")
    try:
        manifest_version = int(manifest.get("manifest_version") or 0)
    except (TypeError, ValueError) as exc:
        raise MigrationError("manifest has an invalid version") from exc
    if manifest_version != MANIFEST_VERSION:
        raise MigrationError("unsupported manifest version")
    if manifest.get("competition") != competition or manifest.get("season") != season:
        raise MigrationError("manifest scope does not match command scope")
    try:
        source_data_revision = int(manifest["source_data_revision"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MigrationError("manifest has no valid source data revision") from exc
    player_rows = validate_rows(
        manifest.get("player_rows") or [],
        columns=PLAYER_COLUMNS,
        key_columns=PLAYER_KEY_COLUMNS,
        competition=competition,
        season=season,
    )
    team_rows = validate_rows(
        manifest.get("team_rows") or [],
        columns=TEAM_COLUMNS,
        key_columns=TEAM_KEY_COLUMNS,
        competition=competition,
        season=season,
    )
    digest = manifest_digest(
        competition,
        season,
        source_data_revision,
        player_rows,
        team_rows,
    )
    if not secrets.compare_digest(str(manifest.get("sha256") or ""), digest):
        raise MigrationError("manifest SHA-256 does not match its rows")
    return player_rows, team_rows, digest


def require_expected_counts(
    player_rows: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
    expected_players: int,
    expected_teams: int,
) -> None:
    actual = (len(player_rows), len(team_rows))
    expected = (expected_players, expected_teams)
    if actual != expected:
        raise MigrationError(
            f"source count precondition failed: actual={actual}, expected={expected}"
        )


def require_manifest_pin(args: argparse.Namespace, actual_digest: str) -> None:
    expected = str(args.expect_manifest_sha256 or "").strip().lower()
    if args.apply and not expected:
        raise MigrationError("--expect-manifest-sha256 is required with --apply")
    if not expected:
        return
    if len(expected) != 64 or any(
        character not in "0123456789abcdef" for character in expected
    ):
        raise MigrationError(
            "--expect-manifest-sha256 must be a 64-character hexadecimal digest"
        )
    if not secrets.compare_digest(expected, actual_digest):
        raise MigrationError(
            "approved manifest SHA-256 mismatch: "
            f"actual={actual_digest}, expected={expected}"
        )


def parse_player_id_map(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        source_id, separator, target_id = str(value or "").partition("=")
        source_id = source_id.strip()
        target_id = target_id.strip()
        if not separator or not source_id or not target_id:
            raise MigrationError(f"invalid --map-player-id value: {value!r}")
        if source_id in result and result[source_id] != target_id:
            raise MigrationError(f"conflicting player ID mapping for {source_id}")
        result[source_id] = target_id
    return result


def apply_player_id_map(
    player_rows: list[dict[str, Any]],
    mapping: dict[str, str],
    *,
    competition: str,
    season: str,
) -> list[dict[str, Any]]:
    used: set[str] = set()
    mapped_rows: list[dict[str, Any]] = []
    for source_row in player_rows:
        row = dict(source_row)
        source_id = str(row.get("player_id") or "")
        if source_id in mapping:
            row["player_id"] = mapping[source_id]
            used.add(source_id)
        mapped_rows.append(row)
    unused = sorted(set(mapping) - used)
    if unused:
        raise MigrationError(f"unused player ID mappings: {unused}")
    return validate_rows(
        mapped_rows,
        columns=PLAYER_COLUMNS,
        key_columns=PLAYER_KEY_COLUMNS,
        competition=competition,
        season=season,
    )


def import_psycopg():
    try:
        import psycopg
    except ImportError as exc:
        raise MigrationError(
            "missing psycopg; install requirements before checking PostgreSQL"
        ) from exc
    return psycopg


def fetch_target_count(cursor: Any, table: str, competition: str, season: str) -> int:
    cursor.execute(
        f"SELECT COUNT(*) FROM {table} WHERE competition_name = %s AND season_name = %s",
        (competition, season),
    )
    return int(cursor.fetchone()[0])


def fetch_data_revision(cursor: Any) -> int:
    cursor.execute(
        "SELECT revision FROM data_revisions WHERE revision_key = %s",
        (DATA_REVISION_KEY,),
    )
    row = cursor.fetchone()
    return int(row[0] or 0) if row else 0


def require_target_counts(cursor: Any, args: argparse.Namespace) -> tuple[int, int]:
    counts = (
        fetch_target_count(
            cursor, "season_player_dimension_stats", args.competition, args.season
        ),
        fetch_target_count(
            cursor, "season_team_dimension_stats", args.competition, args.season
        ),
    )
    expected = (args.expect_target_player_rows, args.expect_target_team_rows)
    if counts != expected:
        raise MigrationError(
            f"target count precondition failed: actual={counts}, expected={expected}"
        )
    return counts


def require_empty_target_expectation(args: argparse.Namespace) -> None:
    expected = (
        int(args.expect_target_player_rows),
        int(args.expect_target_team_rows),
    )
    if expected != (0, 0):
        raise MigrationError(
            "this migration only supports an empty target scope: "
            f"expected_target_counts={expected}"
        )


def require_target_entities(
    cursor: Any,
    player_rows: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
) -> None:
    player_ids = sorted({row["player_id"] for row in player_rows})
    team_ids = sorted(
        {row["team_id"] for row in player_rows if row["team_id"]}
        | {row["team_id"] for row in team_rows}
    )
    cursor.execute(
        "SELECT player_id FROM players WHERE player_id = ANY(%s)",
        (player_ids,),
    )
    existing_players = {str(row[0]) for row in cursor.fetchall()}
    cursor.execute("SELECT team_id FROM teams WHERE team_id = ANY(%s)", (team_ids,))
    existing_teams = {str(row[0]) for row in cursor.fetchall()}
    missing_players = sorted(set(player_ids) - existing_players)
    missing_teams = sorted(set(team_ids) - existing_teams)
    if missing_players or missing_teams:
        raise MigrationError(
            "target entity precondition failed: "
            f"missing_players={missing_players}, missing_teams={missing_teams}"
        )


def require_target_participation(
    cursor: Any,
    player_rows: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
    competition: str,
    season: str,
) -> None:
    cursor.execute(
        """
        SELECT DISTINCT m.played_on, mp.player_id, mp.team_id, mp.seat
        FROM matches AS m
        JOIN match_players AS mp ON mp.match_id = m.match_id
        WHERE m.competition_name = %s AND m.season = %s
        """,
        (competition, season),
    )
    player_evidence = {
        (str(row[0]), str(row[1]), str(row[2]), int(row[3]))
        for row in cursor.fetchall()
    }
    cursor.execute(
        """
        SELECT DISTINCT m.played_on, mp.team_id, mp.seat
        FROM matches AS m
        JOIN match_players AS mp ON mp.match_id = m.match_id
        WHERE m.competition_name = %s AND m.season = %s AND mp.team_id <> ''
        """,
        (competition, season),
    )
    team_evidence = {
        (str(row[0]), str(row[1]), int(row[2])) for row in cursor.fetchall()
    }

    errors: list[str] = []
    for row in player_rows:
        key = (
            row["played_on"],
            row["player_id"],
            row["team_id"],
            int(row["seat"]),
        )
        if key not in player_evidence:
            errors.append(f"player participation missing: {key}")

    for row in team_rows:
        key = (row["played_on"], row["team_id"], int(row["seat"]))
        if key not in team_evidence:
            errors.append(f"team participation missing: {key}")

    if errors:
        preview = "; ".join(errors[:10])
        suffix = f"; and {len(errors) - 10} more" if len(errors) > 10 else ""
        raise MigrationError(f"target participation precondition failed: {preview}{suffix}")


def insert_rows(
    cursor: Any,
    table: str,
    columns: tuple[str, ...],
    rows: list[dict[str, Any]],
) -> None:
    column_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    cursor.executemany(
        f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
        [tuple(row[column] for column in columns) for row in rows],
    )


def fetch_scoped_rows(
    cursor: Any,
    table: str,
    columns: tuple[str, ...],
    key_columns: tuple[str, ...],
    competition: str,
    season: str,
) -> list[dict[str, Any]]:
    column_sql = ", ".join(columns)
    order_sql = ", ".join(key_columns)
    cursor.execute(
        f"SELECT {column_sql} FROM {table} "
        "WHERE competition_name = %s AND season_name = %s "
        f"ORDER BY {order_sql}",
        (competition, season),
    )
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def advance_revision(cursor: Any, expected_revision: int) -> int:
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    cursor.execute(
        """
        UPDATE data_revisions
        SET revision = revision + 1, updated_at_epoch = %s
        WHERE revision_key = %s AND revision = %s
        RETURNING revision
        """,
        (now_epoch, DATA_REVISION_KEY, expected_revision),
    )
    row = cursor.fetchone()
    if not row:
        current = fetch_data_revision(cursor)
        raise MigrationError(
            f"data revision precondition failed: current={current}, expected={expected_revision}"
        )
    return int(row[0])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_pg_restore(pg_restore: str, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            [pg_restore, *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MigrationError(f"could not inspect backup with pg_restore: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown pg_restore error").strip()
        raise MigrationError(f"pg_restore could not read backup: {detail}")
    return result


def database_name_from_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    database_name = unquote(parsed.path.lstrip("/"))
    if parsed.scheme not in {"postgres", "postgresql"} or not database_name:
        raise MigrationError(
            "--database-url must be a PostgreSQL URL with an explicit database name"
        )
    return database_name


def postgres_command_environment(database_url: str) -> tuple[dict[str, str], dict[str, Any]]:
    parsed = urlparse(database_url)
    database_name = database_name_from_url(database_url)
    try:
        port = parsed.port or 5432
    except ValueError as exc:
        raise MigrationError("--database-url has an invalid port") from exc
    if not parsed.hostname or not parsed.username:
        raise MigrationError(
            "--database-url must include an explicit host and username for pg_dump"
        )
    environment = os.environ.copy()
    environment.update(
        {
            "PGHOST": parsed.hostname,
            "PGPORT": str(port),
            "PGUSER": unquote(parsed.username),
            "PGDATABASE": database_name,
        }
    )
    if parsed.password is not None:
        environment["PGPASSWORD"] = unquote(parsed.password)
    query = parse_qs(parsed.query)
    for query_key, environment_key in {
        "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT",
        "sslcert": "PGSSLCERT",
        "sslkey": "PGSSLKEY",
    }.items():
        values = query.get(query_key)
        if values:
            environment[environment_key] = values[-1]
    identity = {
        "database_name": database_name,
        "server_host": parsed.hostname,
        "server_port": port,
        "database_user": unquote(parsed.username),
    }
    return environment, identity


def create_target_backup(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    reference = str(args.backup_reference or "").strip()
    if not reference:
        raise MigrationError("--backup-reference is required with --apply")
    path = Path(reference)
    if not path.is_absolute():
        raise MigrationError("--backup-reference must be an absolute path")
    if path.exists():
        raise MigrationError(f"backup destination already exists: {path}")
    if not path.parent.is_dir():
        raise MigrationError(f"backup directory does not exist: {path.parent}")
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise MigrationError("pg_dump is required to create the production backup")
    environment, identity = postgres_command_environment(args.database_url)
    temporary_path = path.with_name(
        f".{path.name}.{secrets.token_hex(6)}.partial"
    )
    try:
        result = subprocess.run(
            [
                pg_dump,
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--file",
                str(temporary_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
            env=environment,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown pg_dump error").strip()
            raise MigrationError(f"pg_dump failed: {detail}")
        if not temporary_path.is_file() or temporary_path.stat().st_size <= 0:
            raise MigrationError("pg_dump did not create a nonempty backup")
        temporary_path.chmod(0o600)
        os.link(temporary_path, path)
        temporary_path.unlink()
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MigrationError(f"could not create production backup: {exc}") from exc
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return sha256_file(path), identity


def archive_data_revision(pg_restore: str, path: Path) -> int:
    result = run_pg_restore(
        pg_restore,
        ["--data-only", "--table=data_revisions", str(path)],
    )
    copy_match = re.search(r"(?m)^repository\t([0-9]+)\t", result.stdout)
    insert_match = re.search(
        r"(?i)VALUES\s*\(\s*'repository'\s*,\s*([0-9]+)\s*,",
        result.stdout,
    )
    match = copy_match or insert_match
    if not match:
        raise MigrationError(
            "backup does not contain a readable repository data revision"
        )
    return int(match.group(1))


def validate_backup_toc(toc: str, expected_database: str) -> str:
    if not toc.strip():
        raise MigrationError("pg_restore returned an empty backup manifest")
    database_match = re.search(
        r"(?im)^;\s*(?:database|dbname):\s*(.+?)\s*$",
        toc,
    )
    if not database_match:
        raise MigrationError("backup manifest has no database identity")
    archive_database = database_match.group(1).strip()
    if archive_database != expected_database:
        raise MigrationError(
            "backup database identity mismatch: "
            f"archive={archive_database}, target={expected_database}"
        )
    missing_schema_tables = [
        table
        for table in REQUIRED_BACKUP_TABLES
        if not re.search(
            rf"(?m)\bTABLE\s+(?:public\s+)?{re.escape(table)}\b",
            toc,
        )
    ]
    missing_data_tables = [
        table
        for table in REQUIRED_BACKUP_TABLES
        if not re.search(
            rf"(?m)\bTABLE DATA\s+(?:public\s+)?{re.escape(table)}\b",
            toc,
        )
    ]
    if missing_schema_tables or missing_data_tables:
        raise MigrationError(
            "backup is not a full restorable archive: "
            f"missing_schema={missing_schema_tables}, missing_data={missing_data_tables}"
        )
    return archive_database


def verify_backup(
    args: argparse.Namespace,
    expected_sha256: str,
    target_identity: dict[str, Any],
) -> dict[str, Any]:
    reference = str(args.backup_reference or "").strip()
    if not reference:
        raise MigrationError("--backup-reference is required with --apply")
    path = Path(reference)
    if not path.is_absolute():
        raise MigrationError("--backup-reference must be an absolute path")
    if not path.is_file():
        raise MigrationError(f"backup file does not exist: {path}")
    stat = path.stat()
    if stat.st_size <= 0:
        raise MigrationError(f"backup file is empty: {path}")
    expected_sha256 = str(expected_sha256 or "").strip().lower()
    if len(expected_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in expected_sha256
    ):
        raise MigrationError("created backup has an invalid SHA-256 digest")
    actual_sha256 = sha256_file(path)
    if not secrets.compare_digest(actual_sha256, expected_sha256):
        raise MigrationError(
            "backup SHA-256 mismatch: "
            f"actual={actual_sha256}, expected={expected_sha256}"
        )
    now = datetime.now(timezone.utc)
    modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    age = now - modified_at
    if age < timedelta(minutes=-5) or age > timedelta(hours=2):
        raise MigrationError(
            "backup file is not recent enough: "
            f"modified_at={modified_at.isoformat()}, age_seconds={int(age.total_seconds())}"
        )
    pg_restore = shutil.which("pg_restore")
    if not pg_restore:
        raise MigrationError("pg_restore is required to validate the backup")
    result = run_pg_restore(pg_restore, ["--list", str(path)])
    toc = result.stdout
    expected_database = target_identity["database_name"]
    archive_database = validate_backup_toc(toc, expected_database)
    backup_revision = archive_data_revision(pg_restore, path)
    if backup_revision != args.expect_data_revision:
        raise MigrationError(
            "backup data revision mismatch: "
            f"archive={backup_revision}, expected={args.expect_data_revision}"
        )
    return {
        "path": str(path),
        "sha256": actual_sha256,
        "size_bytes": int(stat.st_size),
        "modified_at_utc": modified_at.isoformat(),
        "database_name": archive_database,
        "server_host": target_identity["server_host"],
        "server_port": target_identity["server_port"],
        "database_user": target_identity["database_user"],
        "created_from_target_url": True,
        "data_revision": backup_revision,
        "required_tables": list(REQUIRED_BACKUP_TABLES),
        "pg_restore_list_verified": True,
    }


def record_audit(
    cursor: Any,
    args: argparse.Namespace,
    source_digest: str,
    target_digest: str,
    player_id_map: dict[str, str],
    backup_metadata: dict[str, Any],
    next_revision: int,
) -> str:
    audit_id = "audit_" + secrets.token_hex(12)
    created_at = datetime.now(timezone(timedelta(hours=8))).strftime(
        "%Y-%m-%d %H:%M:%S 中国时间"
    )
    metadata = {
        "competition": args.competition,
        "season": args.season,
        "player_rows": args.expect_player_rows,
        "team_rows": args.expect_team_rows,
        "source_manifest_sha256": source_digest,
        "target_payload_sha256": target_digest,
        "player_id_map": player_id_map,
        "backup": backup_metadata,
        "data_revision": next_revision,
    }
    cursor.execute(
        """
        INSERT INTO audit_logs (
            audit_id, request_id, username, action, target_type, target_id,
            summary, ip_address, created_at, metadata_json
        ) VALUES (%s, '', %s, %s, %s, %s, %s, '', %s, %s)
        """,
        (
            audit_id,
            "codex-production-migration",
            "migrate_season_dimensions",
            "season_scope",
            f"{args.competition}|{args.season}",
            (
                f"Imported {args.expect_player_rows} player and "
                f"{args.expect_team_rows} team dimension rows."
            ),
            created_at,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        ),
    )
    return audit_id


def check_or_apply_target(
    args: argparse.Namespace,
    player_rows: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
    source_digest: str,
    target_digest: str,
    player_id_map: dict[str, str],
) -> None:
    require_empty_target_expectation(args)
    if not args.database_url:
        raise MigrationError("DATABASE_URL is required for target validation")
    if args.apply and args.expect_data_revision is None:
        raise MigrationError("--expect-data-revision is required with --apply")
    if args.apply and not args.create_backup:
        raise MigrationError("--create-backup is required with --apply")
    if args.apply:
        backup_sha256, target_identity = create_target_backup(args)
        backup_metadata = verify_backup(args, backup_sha256, target_identity)
    else:
        backup_metadata = {}

    psycopg = import_psycopg()
    with psycopg.connect(args.database_url) as connection:
        if not args.apply:
            with connection.cursor() as cursor:
                target_counts = require_target_counts(cursor, args)
                require_target_entities(cursor, player_rows, team_rows)
                require_target_participation(
                    cursor,
                    player_rows,
                    team_rows,
                    args.competition,
                    args.season,
                )
                revision = fetch_data_revision(cursor)
            print(
                "Target preflight passed: "
                f"player_rows={target_counts[0]}, team_rows={target_counts[1]}, "
                f"data_revision={revision}"
            )
            return

        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    "LOCK TABLE season_player_dimension_stats, "
                    "season_team_dimension_stats IN SHARE ROW EXCLUSIVE MODE"
                )
                require_target_counts(cursor, args)
                require_target_entities(cursor, player_rows, team_rows)
                require_target_participation(
                    cursor,
                    player_rows,
                    team_rows,
                    args.competition,
                    args.season,
                )
                current_revision = fetch_data_revision(cursor)
                if current_revision != args.expect_data_revision:
                    raise MigrationError(
                        "data revision precondition failed: "
                        f"current={current_revision}, expected={args.expect_data_revision}"
                    )
                insert_rows(
                    cursor,
                    "season_player_dimension_stats",
                    PLAYER_COLUMNS,
                    player_rows,
                )
                insert_rows(
                    cursor,
                    "season_team_dimension_stats",
                    TEAM_COLUMNS,
                    team_rows,
                )
                expected_after = (
                    args.expect_target_player_rows + args.expect_player_rows,
                    args.expect_target_team_rows + args.expect_team_rows,
                )
                actual_after = (
                    fetch_target_count(
                        cursor,
                        "season_player_dimension_stats",
                        args.competition,
                        args.season,
                    ),
                    fetch_target_count(
                        cursor,
                        "season_team_dimension_stats",
                        args.competition,
                        args.season,
                    ),
                )
                if actual_after != expected_after:
                    raise MigrationError(
                        "post-insert count mismatch: "
                        f"actual={actual_after}, expected={expected_after}"
                    )
                persisted_players = fetch_scoped_rows(
                    cursor,
                    "season_player_dimension_stats",
                    PLAYER_COLUMNS,
                    PLAYER_KEY_COLUMNS,
                    args.competition,
                    args.season,
                )
                persisted_teams = fetch_scoped_rows(
                    cursor,
                    "season_team_dimension_stats",
                    TEAM_COLUMNS,
                    TEAM_KEY_COLUMNS,
                    args.competition,
                    args.season,
                )
                persisted_digest = payload_digest(
                    validate_rows(
                        persisted_players,
                        columns=PLAYER_COLUMNS,
                        key_columns=PLAYER_KEY_COLUMNS,
                        competition=args.competition,
                        season=args.season,
                    ),
                    validate_rows(
                        persisted_teams,
                        columns=TEAM_COLUMNS,
                        key_columns=TEAM_KEY_COLUMNS,
                        competition=args.competition,
                        season=args.season,
                    ),
                )
                if not secrets.compare_digest(persisted_digest, target_digest):
                    raise MigrationError(
                        "post-insert SHA-256 mismatch: "
                        f"actual={persisted_digest}, expected={target_digest}"
                    )
                next_revision = advance_revision(cursor, args.expect_data_revision)
                audit_id = record_audit(
                    cursor,
                    args,
                    source_digest,
                    target_digest,
                    player_id_map,
                    backup_metadata,
                    next_revision,
                )

        with connection.cursor() as cursor:
            final_counts = (
                fetch_target_count(
                    cursor,
                    "season_player_dimension_stats",
                    args.competition,
                    args.season,
                ),
                fetch_target_count(
                    cursor,
                    "season_team_dimension_stats",
                    args.competition,
                    args.season,
                ),
            )
            final_revision = fetch_data_revision(cursor)
        print(
            "Migration committed: "
            f"player_rows={final_counts[0]}, team_rows={final_counts[1]}, "
            f"data_revision={final_revision}, audit_id={audit_id}"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.apply and args.write_manifest:
            raise MigrationError("--apply cannot be combined with --write-manifest")
        if args.sqlite_db:
            raw_players, raw_teams, source_data_revision = load_sqlite_rows(
                args.sqlite_db, args.competition, args.season
            )
            manifest = build_manifest(
                args.competition,
                args.season,
                source_data_revision,
                raw_players,
                raw_teams,
            )
            player_rows, team_rows, source_digest = validate_manifest(
                manifest, args.competition, args.season
            )
        else:
            if args.write_manifest:
                raise MigrationError("--write-manifest requires --sqlite-db")
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            player_rows, team_rows, source_digest = validate_manifest(
                manifest, args.competition, args.season
            )

        require_expected_counts(
            player_rows,
            team_rows,
            args.expect_player_rows,
            args.expect_team_rows,
        )
        require_manifest_pin(args, source_digest)
        print(
            "Source validation passed: "
            f"player_rows={len(player_rows)}, team_rows={len(team_rows)}, "
            f"sha256={source_digest}"
        )

        if args.write_manifest:
            args.write_manifest.parent.mkdir(parents=True, exist_ok=True)
            args.write_manifest.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Manifest written: {args.write_manifest}")
            return 0

        player_id_map = parse_player_id_map(args.map_player_id)
        target_player_rows = apply_player_id_map(
            player_rows,
            player_id_map,
            competition=args.competition,
            season=args.season,
        )
        target_digest = payload_digest(target_player_rows, team_rows)
        if player_id_map:
            print(
                "Explicit player ID mapping applied: "
                f"entries={len(player_id_map)}, target_sha256={target_digest}"
            )
        check_or_apply_target(
            args,
            target_player_rows,
            team_rows,
            source_digest,
            target_digest,
            player_id_map,
        )
        if not args.apply:
            print("Dry-run only; PostgreSQL was not modified.")
        return 0
    except (MigrationError, json.JSONDecodeError, OSError, sqlite3.Error) as exc:
        print(f"Migration aborted: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"Migration aborted: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
