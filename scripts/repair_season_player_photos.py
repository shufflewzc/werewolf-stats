#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSET_ROOT = ROOT / "assets" / "players" / "uploads"
DATA_REVISION_KEY = "repository"
MANIFEST_VERSION = 1
DEFAULT_PLAYER_PHOTO = "assets/players/default-player.svg"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ASSET_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*\.(?:png|jpe?g|webp|gif)$")
REQUIRED_BACKUP_TABLES = (
    "audit_logs",
    "data_revisions",
    "matches",
    "match_players",
    "players",
)


class RepairError(RuntimeError):
    pass


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely restore one season's player avatar files and database paths."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, default=DEFAULT_ASSET_ROOT)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--expect-manifest-sha256", required=True)
    parser.add_argument("--expect-count", type=int, required=True)
    parser.add_argument("--expect-scope-player-count", type=int, required=True)
    parser.add_argument("--expect-data-revision", type=int)
    parser.add_argument("--database-backup", type=Path)
    parser.add_argument("--database-backup-sha256", default="")
    parser.add_argument("--asset-backup", type=Path)
    parser.add_argument("--asset-backup-sha256", default="")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalized_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise RepairError(f"manifest entry is missing {label}")
    return text


def validate_manifest(
    manifest_path: Path,
    asset_dir: Path,
    *,
    expected_sha256: str,
    expected_count: int,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if not manifest_path.is_file():
        raise RepairError(f"manifest does not exist: {manifest_path}")
    actual_manifest_sha256 = sha256_file(manifest_path)
    if not SHA256_PATTERN.fullmatch(expected_sha256) or not secrets.compare_digest(
        actual_manifest_sha256, expected_sha256
    ):
        raise RepairError(
            "manifest SHA-256 mismatch: "
            f"actual={actual_manifest_sha256}, expected={expected_sha256}"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RepairError(f"manifest is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise RepairError("manifest top level must be an object")
    if manifest.get("version") != MANIFEST_VERSION:
        raise RepairError(f"unsupported manifest version: {manifest.get('version')}")
    normalized_text(manifest.get("competition"), "competition")
    normalized_text(manifest.get("season"), "season")
    source_archive = manifest.get("source_archive")
    if not isinstance(source_archive, dict) or not SHA256_PATTERN.fullmatch(
        str(source_archive.get("sha256") or "")
    ):
        raise RepairError("manifest source_archive.sha256 is missing or invalid")
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list) or len(raw_entries) != expected_count:
        raise RepairError(
            f"manifest entry count mismatch: actual={len(raw_entries or [])}, expected={expected_count}"
        )
    entries: list[dict[str, str]] = []
    player_ids: set[str] = set()
    asset_files: set[str] = set()
    new_photos: set[str] = set()
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise RepairError("manifest entry must be an object")
        entry = {
            key: normalized_text(raw_entry.get(key), key)
            for key in (
                "player_id",
                "display_name",
                "expected_photo",
                "source_path",
                "source_sha256",
                "asset_file",
                "new_photo",
            )
        }
        if entry["player_id"] in player_ids:
            raise RepairError(f"duplicate player_id in manifest: {entry['player_id']}")
        if entry["asset_file"] in asset_files or entry["new_photo"] in new_photos:
            raise RepairError(f"duplicate destination asset in manifest: {entry['asset_file']}")
        if not SHA256_PATTERN.fullmatch(entry["source_sha256"]):
            raise RepairError(f"invalid source_sha256 for {entry['player_id']}")
        if not ASSET_NAME_PATTERN.fullmatch(entry["asset_file"]):
            raise RepairError(f"unsafe asset filename for {entry['player_id']}: {entry['asset_file']}")
        expected_photo = f"assets/players/uploads/{entry['asset_file']}"
        if entry["new_photo"] != expected_photo:
            raise RepairError(
                f"new_photo does not match asset_file for {entry['player_id']}: {entry['new_photo']}"
            )
        source_file = asset_dir / entry["asset_file"]
        if not source_file.is_file():
            raise RepairError(f"prepared asset is missing: {source_file}")
        actual_source_sha256 = sha256_file(source_file)
        if not secrets.compare_digest(actual_source_sha256, entry["source_sha256"]):
            raise RepairError(
                f"prepared asset SHA-256 mismatch for {entry['player_id']}: "
                f"actual={actual_source_sha256}, expected={entry['source_sha256']}"
            )
        validate_image_signature(source_file)
        player_ids.add(entry["player_id"])
        asset_files.add(entry["asset_file"])
        new_photos.add(entry["new_photo"])
        entries.append(entry)
    unexpected_assets = sorted(
        path.name
        for path in asset_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
        and path.name not in asset_files
    )
    if unexpected_assets:
        raise RepairError(
            "prepared asset directory contains files outside the manifest: "
            + ", ".join(unexpected_assets[:5])
        )
    entries.sort(key=lambda item: item["player_id"])
    if canonical_json_sha256(entries) != str(manifest.get("entries_sha256") or ""):
        raise RepairError("manifest entries_sha256 mismatch")
    return manifest, entries


def validate_image_signature(path: Path) -> None:
    payload = path.read_bytes()[:16]
    suffix = path.suffix.lower()
    valid = {
        ".png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": payload.startswith(b"\xff\xd8\xff"),
        ".jpeg": payload.startswith(b"\xff\xd8\xff"),
        ".webp": payload.startswith(b"RIFF") and payload[8:12] == b"WEBP",
        ".gif": payload.startswith((b"GIF87a", b"GIF89a")),
    }.get(suffix, False)
    if not valid:
        raise RepairError(f"prepared asset has an invalid {suffix} signature: {path}")


def run_command(command: list[str], *, label: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RepairError(f"{label} failed: {detail}")
    return completed


def verify_recent_file(path: Path | None, expected_sha256: str, label: str) -> dict[str, Any]:
    if path is None or not path.is_absolute() or not path.is_file():
        raise RepairError(f"{label} must be an existing absolute file")
    if not SHA256_PATTERN.fullmatch(expected_sha256):
        raise RepairError(f"{label} expected SHA-256 is invalid")
    stat = path.stat()
    age_seconds = time.time() - stat.st_mtime
    if age_seconds < -60 or age_seconds > 7200:
        raise RepairError(f"{label} is not recent enough: age_seconds={int(age_seconds)}")
    actual_sha256 = sha256_file(path)
    if not secrets.compare_digest(actual_sha256, expected_sha256):
        raise RepairError(
            f"{label} SHA-256 mismatch: actual={actual_sha256}, expected={expected_sha256}"
        )
    return {"path": str(path), "sha256": actual_sha256, "size_bytes": stat.st_size}


def database_name_from_url(database_url: str) -> str:
    return unquote(urlparse(database_url).path.lstrip("/"))


def verify_database_backup(
    path: Path | None,
    expected_sha256: str,
    database_url: str,
    expected_revision: int,
) -> dict[str, Any]:
    metadata = verify_recent_file(path, expected_sha256, "database backup")
    pg_restore = shutil.which("pg_restore")
    if not pg_restore:
        raise RepairError("pg_restore is required to validate the database backup")
    toc = run_command([pg_restore, "--list", str(path)], label="database backup inspection").stdout
    archive_database_match = re.search(r"^;\s*dbname:\s*(\S+)\s*$", toc, re.MULTILINE)
    if not archive_database_match:
        raise RepairError("database backup does not declare its database name")
    archive_database = archive_database_match.group(1)
    expected_database = database_name_from_url(database_url)
    if archive_database and archive_database != expected_database:
        raise RepairError(
            f"database backup target mismatch: archive={archive_database}, expected={expected_database}"
        )
    missing_schema = [
        table
        for table in REQUIRED_BACKUP_TABLES
        if not re.search(rf"\bTABLE\s+\S+\s+{re.escape(table)}\b", toc)
    ]
    missing_data = [
        table
        for table in REQUIRED_BACKUP_TABLES
        if not re.search(rf"\bTABLE DATA\s+\S+\s+{re.escape(table)}\b", toc)
    ]
    if missing_schema or missing_data:
        raise RepairError(
            "database backup is incomplete: "
            f"missing_schema={missing_schema}, missing_data={missing_data}"
        )
    revision_sql = run_command(
        [pg_restore, "--data-only", "--table=data_revisions", "--file=-", str(path)],
        label="database backup revision inspection",
    ).stdout
    revision_match = re.search(r"^repository\t(\d+)\t", revision_sql, re.MULTILINE)
    if not revision_match:
        revision_match = re.search(
            r"INSERT INTO\s+\S*data_revisions\s+.*?VALUES\s*\(\s*'repository'\s*,\s*(\d+)",
            revision_sql,
            re.IGNORECASE | re.DOTALL,
        )
    if not revision_match:
        raise RepairError("database backup repository revision could not be read")
    backup_revision = int(revision_match.group(1))
    if backup_revision != expected_revision:
        raise RepairError(
            f"database backup revision mismatch: archive={backup_revision}, expected={expected_revision}"
        )
    metadata["database_name"] = archive_database or expected_database
    metadata["data_revision"] = backup_revision
    metadata["required_tables"] = list(REQUIRED_BACKUP_TABLES)
    return metadata


def verify_asset_backup(path: Path | None, expected_sha256: str) -> dict[str, Any]:
    metadata = verify_recent_file(path, expected_sha256, "asset backup")
    assert path is not None
    try:
        with tarfile.open(path, "r:gz") as archive:
            members = archive.getmembers()
    except (OSError, tarfile.TarError) as exc:
        raise RepairError(f"asset backup is not a readable tar.gz: {exc}") from exc
    unsafe = [
        member.name
        for member in members
        if member.name.startswith("/") or ".." in Path(member.name).parts
    ]
    if unsafe:
        raise RepairError("asset backup contains unsafe paths: " + ", ".join(unsafe[:5]))
    if not any(member.name.startswith("assets/players/uploads/") for member in members):
        raise RepairError("asset backup does not contain assets/players/uploads")
    metadata["entry_count"] = len(members)
    return metadata


def import_psycopg():
    try:
        import psycopg
    except ImportError as exc:
        raise RepairError("psycopg is required to update PostgreSQL") from exc
    return psycopg


def fetch_scope_players(cursor: Any, competition: str, season: str) -> dict[str, dict[str, str]]:
    cursor.execute(
        """
        SELECT DISTINCT p.player_id, p.display_name, p.photo
        FROM players p
        JOIN match_players mp ON mp.player_id = p.player_id
        JOIN matches m ON m.match_id = mp.match_id
        WHERE m.competition_name = %s AND m.season = %s
        ORDER BY p.player_id
        """,
        (competition, season),
    )
    return {
        str(row[0]): {
            "player_id": str(row[0]),
            "display_name": str(row[1]),
            "photo": str(row[2]),
        }
        for row in cursor.fetchall()
    }


def fetch_revision(cursor: Any, *, lock: bool = False) -> int:
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        f"SELECT revision FROM data_revisions WHERE revision_key = %s{suffix}",
        (DATA_REVISION_KEY,),
    )
    row = cursor.fetchone()
    if not row:
        raise RepairError("repository data revision row is missing")
    return int(row[0])


def require_target_state(
    cursor: Any,
    manifest: dict[str, Any],
    entries: list[dict[str, str]],
    expected_scope_count: int,
) -> dict[str, dict[str, str]]:
    scope_players = fetch_scope_players(cursor, manifest["competition"], manifest["season"])
    if len(scope_players) != expected_scope_count:
        raise RepairError(
            f"scope player count mismatch: actual={len(scope_players)}, expected={expected_scope_count}"
        )
    for entry in entries:
        target = scope_players.get(entry["player_id"])
        if target is None:
            raise RepairError(f"player does not participate in target scope: {entry['player_id']}")
        if target["display_name"] != entry["display_name"]:
            raise RepairError(
                f"display_name mismatch for {entry['player_id']}: "
                f"actual={target['display_name']}, expected={entry['display_name']}"
            )
        if target["photo"] != entry["expected_photo"]:
            raise RepairError(
                f"photo precondition failed for {entry['player_id']}: "
                f"actual={target['photo']}, expected={entry['expected_photo']}"
            )
    return scope_players


def install_assets(
    entries: list[dict[str, str]], asset_dir: Path, asset_root: Path
) -> list[Path]:
    asset_root.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for entry in entries:
        source = asset_dir / entry["asset_file"]
        destination = asset_root / entry["asset_file"]
        if destination.exists():
            if not destination.is_file() or sha256_file(destination) != entry["source_sha256"]:
                raise RepairError(f"destination asset already exists with different content: {destination}")
            continue
        temporary = asset_root / f".{entry['asset_file']}.{secrets.token_hex(8)}.tmp"
        try:
            with source.open("rb") as source_handle, temporary.open("xb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle)
                target_handle.flush()
                os.fsync(target_handle.fileno())
            os.chmod(temporary, 0o644)
            try:
                os.link(temporary, destination)
            except FileExistsError:
                if not destination.is_file() or sha256_file(destination) != entry["source_sha256"]:
                    raise RepairError(
                        f"destination asset appeared with different content: {destination}"
                    )
            else:
                created.append(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return created


def cleanup_created_assets(created: list[Path]) -> None:
    for path in created:
        path.unlink(missing_ok=True)


def record_audit(
    cursor: Any,
    manifest: dict[str, Any],
    entries: list[dict[str, str]],
    manifest_sha256: str,
    database_backup: dict[str, Any],
    asset_backup: dict[str, Any],
    next_revision: int,
) -> str:
    audit_id = "audit_" + secrets.token_hex(12)
    created_at = datetime.now(timezone(timedelta(hours=8))).strftime(
        "%Y-%m-%d %H:%M:%S 中国时间"
    )
    metadata = {
        "competition": manifest["competition"],
        "season": manifest["season"],
        "player_count": len(entries),
        "source_archive": manifest["source_archive"],
        "manifest_sha256": manifest_sha256,
        "entries_sha256": manifest["entries_sha256"],
        "database_backup": database_backup,
        "asset_backup": asset_backup,
        "data_revision": next_revision,
        "changes": [
            {
                "player_id": entry["player_id"],
                "old_photo": entry["expected_photo"],
                "new_photo": entry["new_photo"],
                "source_path": entry["source_path"],
                "source_sha256": entry["source_sha256"],
            }
            for entry in entries
        ],
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
            "codex-production-repair",
            "season_player_photo.restore",
            "season_scope",
            f"{manifest['competition']}|{manifest['season']}",
            f"Restored {len(entries)} player avatars and their asset files.",
            created_at,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        ),
    )
    return audit_id


def apply_repair(
    args: argparse.Namespace,
    manifest: dict[str, Any],
    entries: list[dict[str, str]],
    manifest_sha256: str,
    database_backup: dict[str, Any],
    asset_backup: dict[str, Any],
) -> tuple[str, int]:
    if args.expect_data_revision is None:
        raise RepairError("--expect-data-revision is required with --apply")
    created = install_assets(entries, args.asset_dir.resolve(), args.asset_root.resolve())
    psycopg = import_psycopg()
    committed = False
    try:
        with psycopg.connect(args.database_url) as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "LOCK TABLE players, matches, match_players, data_revisions, audit_logs "
                        "IN SHARE ROW EXCLUSIVE MODE"
                    )
                    require_target_state(cursor, manifest, entries, args.expect_scope_player_count)
                    revision = fetch_revision(cursor, lock=True)
                    if revision != args.expect_data_revision:
                        raise RepairError(
                            f"data revision precondition failed: actual={revision}, "
                            f"expected={args.expect_data_revision}"
                        )
                    for entry in entries:
                        cursor.execute(
                            "UPDATE players SET photo = %s WHERE player_id = %s AND photo = %s",
                            (entry["new_photo"], entry["player_id"], entry["expected_photo"]),
                        )
                        if cursor.rowcount != 1:
                            raise RepairError(f"player update CAS failed: {entry['player_id']}")
                    cursor.execute(
                        """
                        UPDATE data_revisions
                        SET revision = revision + 1, updated_at_epoch = %s
                        WHERE revision_key = %s AND revision = %s
                        RETURNING revision
                        """,
                        (int(time.time()), DATA_REVISION_KEY, args.expect_data_revision),
                    )
                    revision_row = cursor.fetchone()
                    if not revision_row:
                        raise RepairError("data revision CAS failed")
                    next_revision = int(revision_row[0])
                    audit_id = record_audit(
                        cursor,
                        manifest,
                        entries,
                        manifest_sha256,
                        database_backup,
                        asset_backup,
                        next_revision,
                    )
            committed = True
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM players WHERE player_id = ANY(%s) "
                    "AND photo = ANY(%s)",
                    ([entry["player_id"] for entry in entries], [entry["new_photo"] for entry in entries]),
                )
                restored_count = int(cursor.fetchone()[0])
                if restored_count != len(entries):
                    raise RepairError(
                        f"post-commit database validation failed: actual={restored_count}, expected={len(entries)}"
                    )
    except Exception:
        if not committed:
            cleanup_created_assets(created)
        raise
    return audit_id, next_revision


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if not args.database_url.startswith(("postgres://", "postgresql://")):
            raise RepairError("a PostgreSQL --database-url is required")
        expected_manifest_sha256 = args.expect_manifest_sha256.lower()
        manifest, entries = validate_manifest(
            args.manifest.resolve(),
            args.asset_dir.resolve(),
            expected_sha256=expected_manifest_sha256,
            expected_count=args.expect_count,
        )
        psycopg = import_psycopg()
        with psycopg.connect(args.database_url) as connection:
            with connection.cursor() as cursor:
                require_target_state(cursor, manifest, entries, args.expect_scope_player_count)
                revision = fetch_revision(cursor)
        print(
            "Target preflight passed: "
            f"competition={manifest['competition']}, season={manifest['season']}, "
            f"players={len(entries)}, scope_players={args.expect_scope_player_count}, "
            f"data_revision={revision}"
        )
        if not args.apply:
            return 0
        if revision != args.expect_data_revision:
            raise RepairError(
                f"data revision precondition failed: actual={revision}, expected={args.expect_data_revision}"
            )
        database_backup = verify_database_backup(
            args.database_backup,
            args.database_backup_sha256.lower(),
            args.database_url,
            args.expect_data_revision,
        )
        asset_backup = verify_asset_backup(
            args.asset_backup,
            args.asset_backup_sha256.lower(),
        )
        audit_id, next_revision = apply_repair(
            args,
            manifest,
            entries,
            expected_manifest_sha256,
            database_backup,
            asset_backup,
        )
        print(
            f"Repair committed: players={len(entries)}, data_revision={next_revision}, audit_id={audit_id}"
        )
        return 0
    except Exception as exc:
        print(f"photo repair failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
