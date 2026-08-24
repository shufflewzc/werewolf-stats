#!/usr/bin/env python3

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
import zipfile

from competition_meta import (
    load_scoring_rule_templates,
    load_season_catalog,
    load_series_catalog,
)
from schema_version import REQUIRED_SCHEMA_VERSION
from sqlite_store import get_data_revision, load_repository_data
from validate_data import is_non_profile_player_id


ROOT = Path(__file__).resolve().parents[1]
FORMAT_NAME = "werewolf-historical-tournament-dataset"
FORMAT_VERSION = 2
PUBLIC_REPOSITORY_KEYS = (
    "teams",
    "players",
    "matches",
    "season_player_dimension_stats",
    "season_team_dimension_stats",
)
MEDIA_PREFIXES = (
    Path("assets/players/uploads"),
    Path("assets/teams/uploads"),
)
ALLOWED_MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_MEDIA_FILES = 2_000
MAX_MEDIA_BYTES = 20 * 1024 * 1024
EXCLUDED_DATA = [
    "staff_accounts",
    "members",
    "openid",
    "sessions",
    "logs",
    "orders",
    "payments",
    "refunds",
    "follows",
    "player_claims",
    "claim_disputes",
    "guilds",
    "honors",
]

Scope = tuple[str, str]
METADATA_AUDIT_FIELDS = {"created_by", "created_on", "updated_at"}


class DatasetExportError(ValueError):
    pass


def json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize_scope(competition_name: object, season_name: object) -> Scope:
    return str(competition_name or "").strip(), str(season_name or "").strip()


def scope_payload(scope: Scope) -> dict[str, str]:
    return {"competition_name": scope[0], "season_name": scope[1]}


def match_scope(match: dict[str, Any]) -> Scope:
    return normalize_scope(match.get("competition_name"), match.get("season"))


def team_scope(team: dict[str, Any]) -> Scope:
    return normalize_scope(team.get("competition_name"), team.get("season_name"))


def dimension_scope(row: dict[str, Any]) -> Scope:
    return normalize_scope(row.get("competition_name"), row.get("season_name"))


def catalog_scope(entry: dict[str, Any]) -> Scope:
    return normalize_scope(entry.get("competition_name"), entry.get("season_name"))


def sanitize_metadata_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in entry.items()
        if str(key) not in METADATA_AUDIT_FIELDS
    }


def sanitize_repository(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    public_data = {
        key: [dict(item) for item in data.get(key, []) if isinstance(item, dict)]
        for key in PUBLIC_REPOSITORY_KEYS
    }
    public_data["teams"] = [
        {**team, "guild_id": ""}
        for team in public_data["teams"]
    ]
    return public_data


def available_scopes(
    data: dict[str, Any],
    season_catalog: Iterable[dict[str, Any]] = (),
) -> list[Scope]:
    scopes = {
        *(match_scope(item) for item in data.get("matches", []) if isinstance(item, dict)),
        *(team_scope(item) for item in data.get("teams", []) if isinstance(item, dict)),
        *(
            dimension_scope(item)
            for key in ("season_player_dimension_stats", "season_team_dimension_stats")
            for item in data.get(key, [])
            if isinstance(item, dict)
        ),
        *(catalog_scope(item) for item in season_catalog if isinstance(item, dict)),
    }
    return sorted(scope for scope in scopes if scope[0] and scope[1])


def _require_references(
    *,
    referenced_ids: set[str],
    available_ids: set[str],
    label: str,
) -> None:
    missing_ids = sorted(referenced_ids - available_ids)
    if missing_ids:
        raise DatasetExportError(
            f"所选赛季存在找不到的{label}引用：" + "、".join(missing_ids[:20])
        )


def select_public_data(
    data: dict[str, Any],
    selected_scopes: set[Scope],
) -> dict[str, list[dict[str, Any]]]:
    if not selected_scopes:
        raise DatasetExportError("至少需要选择一个赛事赛季。")

    public_data = sanitize_repository(data)
    selected_teams = [
        team for team in public_data["teams"] if team_scope(team) in selected_scopes
    ]
    selected_matches = [
        match for match in public_data["matches"] if match_scope(match) in selected_scopes
    ]
    selected_player_dimensions = [
        row
        for row in public_data["season_player_dimension_stats"]
        if dimension_scope(row) in selected_scopes
    ]
    selected_team_dimensions = [
        row
        for row in public_data["season_team_dimension_stats"]
        if dimension_scope(row) in selected_scopes
    ]

    team_ids = {
        str(team.get("team_id") or "").strip()
        for team in selected_teams
        if str(team.get("team_id") or "").strip()
    }
    referenced_team_ids: set[str] = {
        str(row.get("team_id") or "").strip()
        for row in [*selected_player_dimensions, *selected_team_dimensions]
        if str(row.get("team_id") or "").strip()
    }
    referenced_player_ids: set[str] = {
        str(row.get("player_id") or "").strip()
        for row in selected_player_dimensions
        if str(row.get("player_id") or "").strip()
    }

    for team in selected_teams:
        referenced_player_ids.update(
            str(player_id or "").strip()
            for player_id in team.get("members", [])
            if str(player_id or "").strip()
        )
        captain_player_id = str(team.get("captain_player_id") or "").strip()
        if captain_player_id:
            referenced_player_ids.add(captain_player_id)

    for match in selected_matches:
        for participant in match.get("players", []):
            if not isinstance(participant, dict):
                continue
            player_id = str(participant.get("player_id") or "").strip()
            team_id = str(participant.get("team_id") or "").strip()
            if player_id and not is_non_profile_player_id(player_id):
                referenced_player_ids.add(player_id)
            if team_id:
                referenced_team_ids.add(team_id)
        for field_name in ("mvp_player_id", "svp_player_id", "scapegoat_player_id"):
            player_id = str(match.get(field_name) or "").strip()
            if player_id and not is_non_profile_player_id(player_id):
                referenced_player_ids.add(player_id)

    _require_references(
        referenced_ids=referenced_team_ids,
        available_ids=team_ids,
        label="战队",
    )

    players_by_id = {
        str(player.get("player_id") or "").strip(): player
        for player in public_data["players"]
        if str(player.get("player_id") or "").strip()
    }
    _require_references(
        referenced_ids=referenced_player_ids,
        available_ids=set(players_by_id),
        label="选手",
    )
    selected_players = [
        players_by_id[player_id]
        for player_id in sorted(referenced_player_ids)
    ]
    cross_scope_players = [
        str(player.get("player_id") or "")
        for player in selected_players
        if str(player.get("team_id") or "").strip()
        and str(player.get("team_id") or "").strip() not in team_ids
    ]
    if cross_scope_players:
        raise DatasetExportError(
            "所选赛季的选手档案指向范围外战队：" + "、".join(cross_scope_players[:20])
        )

    return {
        "teams": sorted(selected_teams, key=lambda item: str(item.get("team_id") or "")),
        "players": selected_players,
        "matches": sorted(
            selected_matches,
            key=lambda item: (
                str(item.get("played_on") or ""),
                int(item.get("round") or 0),
                int(item.get("game_no") or 0),
                str(item.get("match_id") or ""),
            ),
        ),
        "season_player_dimension_stats": sorted(
            selected_player_dimensions,
            key=lambda item: (
                *dimension_scope(item),
                str(item.get("played_on") or ""),
                str(item.get("player_id") or ""),
            ),
        ),
        "season_team_dimension_stats": sorted(
            selected_team_dimensions,
            key=lambda item: (
                *dimension_scope(item),
                str(item.get("played_on") or ""),
                str(item.get("team_id") or ""),
                int(item.get("seat") or 0),
            ),
        ),
    }


def select_metadata(
    *,
    series_catalog: list[dict[str, Any]],
    season_catalog: list[dict[str, Any]],
    scoring_rule_templates: list[dict[str, Any]],
    selected_scopes: set[Scope],
    selected_team_ids: set[str],
) -> dict[str, list[dict[str, Any]]]:
    competition_names = {scope[0] for scope in selected_scopes}
    selected_series = [
        sanitize_metadata_entry(entry)
        for entry in series_catalog
        if str(entry.get("competition_name") or "").strip() in competition_names
    ]
    selected_seasons = [
        sanitize_metadata_entry(entry)
        for entry in season_catalog
        if catalog_scope(entry) in selected_scopes
    ]
    missing_catalog_scopes = selected_scopes - {
        catalog_scope(entry) for entry in selected_seasons
    }
    if missing_catalog_scopes:
        labels = [f"{competition} / {season}" for competition, season in sorted(missing_catalog_scopes)]
        raise DatasetExportError("所选赛季缺少赛季目录：" + "、".join(labels[:20]))

    for entry in selected_seasons:
        registered_team_ids = {
            str(team_id or "").strip()
            for team_id in entry.get("registered_team_ids", [])
            if str(team_id or "").strip()
        }
        _require_references(
            referenced_ids=registered_team_ids,
            available_ids=selected_team_ids,
            label="已报名战队",
        )

    return {
        "series_catalog": sorted(
            selected_series,
            key=lambda item: str(item.get("competition_name") or ""),
        ),
        "season_catalog": sorted(
            selected_seasons,
            key=lambda item: (*catalog_scope(item), str(item.get("series_slug") or "")),
        ),
        "scoring_rule_templates": sorted(
            (sanitize_metadata_entry(entry) for entry in scoring_rule_templates),
            key=lambda item: str(item.get("slug") or ""),
        ),
    }


def _is_upload_path(relative: Path) -> bool:
    return any(relative == prefix or prefix in relative.parents for prefix in MEDIA_PREFIXES)


def valid_image_header(path: Path) -> bool:
    with path.open("rb") as source:
        payload = source.read(16)
    suffix = path.suffix.lower()
    return {
        ".png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": payload.startswith(b"\xff\xd8\xff"),
        ".jpeg": payload.startswith(b"\xff\xd8\xff"),
        ".gif": payload.startswith((b"GIF87a", b"GIF89a")),
        ".webp": len(payload) >= 12 and payload.startswith(b"RIFF") and payload[8:12] == b"WEBP",
    }.get(suffix, False)


def referenced_media(data: dict[str, Any], root: Path = ROOT) -> list[Path]:
    root = root.resolve()
    values = {
        str(team.get("logo") or "").strip()
        for team in data.get("teams", [])
    } | {
        str(player.get("photo") or "").strip()
        for player in data.get("players", [])
    }
    resolved: list[Path] = []
    for value in sorted(values):
        if not value or value.startswith(("http://", "https://")):
            continue
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise DatasetExportError(f"媒体路径不安全：{value}")
        if not _is_upload_path(relative):
            continue
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise DatasetExportError(f"媒体路径越界：{value}") from exc
        if not candidate.is_file():
            raise DatasetExportError(f"引用的媒体文件不存在：{value}")
        if candidate.stat().st_size > MAX_MEDIA_BYTES:
            raise DatasetExportError(f"引用的媒体文件超过 20 MB：{value}")
        if candidate.suffix.lower() not in ALLOWED_MEDIA_SUFFIXES or not valid_image_header(candidate):
            raise DatasetExportError(f"引用的媒体文件类型或文件头不正确：{value}")
        resolved.append(candidate)
    if len(resolved) > MAX_MEDIA_FILES:
        raise DatasetExportError(f"引用的媒体文件超过 {MAX_MEDIA_FILES} 个。")
    return resolved


def scope_counts(data: dict[str, list[dict[str, Any]]], scope: Scope) -> dict[str, Any]:
    scoped_teams = [team for team in data["teams"] if team_scope(team) == scope]
    team_ids = {str(team.get("team_id") or "") for team in scoped_teams}
    matches = [match for match in data["matches"] if match_scope(match) == scope]
    player_ids = {
        str(participant.get("player_id") or "")
        for match in matches
        for participant in match.get("players", [])
        if isinstance(participant, dict)
        and str(participant.get("player_id") or "")
        and not is_non_profile_player_id(str(participant.get("player_id") or ""))
    } | {
        str(player_id or "")
        for team in scoped_teams
        for player_id in team.get("members", [])
        if str(player_id or "")
    } | {
        str(team.get("captain_player_id") or "")
        for team in scoped_teams
        if str(team.get("captain_player_id") or "")
    } | {
        str(row.get("player_id") or "")
        for row in data["season_player_dimension_stats"]
        if dimension_scope(row) == scope and str(row.get("player_id") or "")
    }
    for match in matches:
        player_ids.update(
            player_id
            for field_name in ("mvp_player_id", "svp_player_id", "scapegoat_player_id")
            if (player_id := str(match.get(field_name) or ""))
            and not is_non_profile_player_id(player_id)
        )
    return {
        **scope_payload(scope),
        "teams": len(team_ids),
        "players": len(player_ids),
        "matches": len(matches),
        "match_players": sum(len(match.get("players", [])) for match in matches),
        "season_player_dimension_stats": sum(
            1 for row in data["season_player_dimension_stats"] if dimension_scope(row) == scope
        ),
        "season_team_dimension_stats": sum(
            1 for row in data["season_team_dimension_stats"] if dimension_scope(row) == scope
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export selected historical tournament seasons; no user or commerce data is included."
    )
    parser.add_argument("output", nargs="?", type=Path)
    parser.add_argument("--list-scopes", action="store_true", help="List available competition/season pairs and exit.")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--all-scopes", action="store_true", help="Export every available season.")
    selection.add_argument(
        "--scope",
        nargs=2,
        action="append",
        metavar=("COMPETITION", "SEASON"),
        help="Export one exact competition/season pair. May be repeated.",
    )
    parser.add_argument("--no-media", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_data = load_repository_data()
    series_catalog = load_series_catalog(source_data)
    season_catalog = load_season_catalog(source_data)
    templates = load_scoring_rule_templates()
    scopes = available_scopes(source_data, season_catalog)

    if args.list_scopes:
        print(
            json.dumps(
                {"scopes": [scope_payload(scope) for scope in scopes]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.output is None:
        raise SystemExit("缺少输出 ZIP 路径。")
    if not args.all_scopes and not args.scope:
        raise SystemExit("必须显式指定 --all-scopes 或至少一个 --scope。")

    selected_scopes = set(scopes if args.all_scopes else [normalize_scope(*item) for item in args.scope])
    unknown_scopes = selected_scopes - set(scopes)
    if unknown_scopes:
        labels = [f"{competition} / {season}" for competition, season in sorted(unknown_scopes)]
        raise SystemExit("找不到要导出的赛事赛季：" + "、".join(labels))

    try:
        data = select_public_data(source_data, selected_scopes)
        selected_team_ids = {
            str(team.get("team_id") or "") for team in data["teams"]
        }
        metadata = select_metadata(
            series_catalog=series_catalog,
            season_catalog=season_catalog,
            scoring_rule_templates=templates,
            selected_scopes=selected_scopes,
            selected_team_ids=selected_team_ids,
        )
        media_files = [] if args.no_media else referenced_media(data)
    except DatasetExportError as exc:
        raise SystemExit(f"导出预检失败：{exc}") from exc

    repository_payload = json_bytes(data)
    metadata_payload = json_bytes(metadata)
    files = {
        "repository.json": repository_payload,
        "metadata.json": metadata_payload,
    }
    media_payloads = {
        "media/" + str(path.relative_to(ROOT)): path.read_bytes()
        for path in media_files
    }
    source_revision = int(source_data.get("_data_revision") or 0)
    final_revision = get_data_revision()
    if final_revision != source_revision:
        raise SystemExit(
            f"导出期间源数据版本从 {source_revision} 变为 {final_revision}，请重新导出。"
        )
    manifest = {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "schema_version": REQUIRED_SCHEMA_VERSION,
        "source_data_revision": source_revision,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scopes": [scope_payload(scope) for scope in sorted(selected_scopes)],
        "counts": {key: len(value) for key, value in data.items()},
        "scope_counts": [scope_counts(data, scope) for scope in sorted(selected_scopes)],
        "excluded": EXCLUDED_DATA,
        "files": {name: sha256(payload) for name, payload in files.items()},
        "media": [str(path.relative_to(ROOT)) for path in media_files],
        "media_files": {name: sha256(payload) for name, payload in media_payloads.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
        archive.writestr("manifest.json", json_bytes(manifest))
        for name, payload in media_payloads.items():
            archive.writestr(name, payload)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
