#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import difflib
import html
from io import BytesIO
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

try:
    from PIL import Image, ImageOps
except ImportError:  # Pillow is bundled in the macOS app helper.
    Image = None
    ImageOps = None

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
DEFAULT_OUTPUT_ZIP = "matched-player-photos.zip"
DEFAULT_REPORT_CSV = "matched-player-photos-report.csv"
DEFAULT_REPORT_JSON = "matched-player-photos-report.json"
DEFAULT_REPORT_HTML = "matched-player-photos-preview.html"
DEFAULT_SITE_URL = "https://wolf.metauniverse-cn.xyz"
DEFAULT_API_LIMIT = 100
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
COMPRESSED_TARGET_BYTES = 4 * 1024 * 1024
COMPRESSED_MAX_DIMENSION = 2400
MIN_COMPRESSED_TARGET_BYTES = 96 * 1024
ZIP_PAYLOAD_BUDGET_BYTES = 42 * 1024 * 1024
MAX_OUTPUT_ZIP_BYTES = 45 * 1024 * 1024
IMAGE_SIGNATURES = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".webp": (b"RIFF",),
    ".gif": (b"GIF87a", b"GIF89a"),
}
GENERIC_FILENAME_WORDS = (
    "选手头像",
    "队员头像",
    "个人头像",
    "头像",
    "选手照片",
    "队员照片",
    "照片",
    "选手",
    "队员",
    "avatar",
    "profile",
    "photo",
    "image",
    "img",
)
COPY_SUFFIX_PATTERN = re.compile(
    r"(?:[\s._-]*(?:副本|拷贝|copy))?[\s._-]*[\(（\[]\d+[\)）\]]$",
    re.IGNORECASE,
)
TOKEN_SPLIT_PATTERN = re.compile(r"[\s._\-—–+()（）\[\]【】{}]+")


@dataclass(frozen=True)
class Player:
    player_id: str
    display_name: str
    team_id: str = ""
    team_name: str = ""
    appearances: str = ""
    photo: str = ""


@dataclass(frozen=True)
class PhotoMatch:
    path: Path
    player: Player | None
    status: str
    method: str = ""
    reason: str = ""
    suggestion: str = ""


@dataclass(frozen=True)
class ManualSelections:
    assignments: dict[str, str]
    rejected_sources: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CompressionResult:
    original_bytes: int
    output_bytes: int
    output_extension: str

    @property
    def note(self) -> str:
        original_mb = self.original_bytes / 1024 / 1024
        output_mb = self.output_bytes / 1024 / 1024
        return f"已自动压缩 {original_mb:.1f} MB → {output_mb:.1f} MB"


def normalize_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(character for character in normalized if character.isalnum())


def filename_variants(path: Path) -> set[str]:
    stem = unicodedata.normalize("NFKC", path.stem).strip()
    without_copy_suffix = COPY_SUFFIX_PATTERN.sub("", stem).strip()
    variants = {normalize_key(stem), normalize_key(without_copy_suffix)}

    tokens = [
        normalize_key(token)
        for token in TOKEN_SPLIT_PATTERN.split(without_copy_suffix)
        if normalize_key(token)
    ]
    variants.update(tokens)

    cleaned = without_copy_suffix
    for word in GENERIC_FILENAME_WORDS:
        cleaned = re.sub(re.escape(word), "", cleaned, flags=re.IGNORECASE)
    variants.add(normalize_key(cleaned))
    return {variant for variant in variants if variant}


def find_roster_csv(folder: Path, explicit_path: str = "") -> Path:
    if explicit_path:
        roster_path = Path(explicit_path).expanduser()
        if not roster_path.is_absolute():
            roster_path = folder / roster_path
        if roster_path.is_file():
            return roster_path.resolve()
        raise ValueError(f"队员名单 CSV 不存在：{roster_path}")

    candidates = [
        path
        for path in folder.glob("*.csv")
        if path.name != DEFAULT_REPORT_CSV
        and not path.name.startswith("matched-player-photos-report")
    ]
    if not candidates:
        raise ValueError(
            "当前文件夹没有找到队员名单 CSV。请从后台导出名单，"
            "或使用 --from-site --competition ... --season ... 读取线上名单。"
        )
    if len(candidates) > 1:
        names = "、".join(path.name for path in candidates)
        raise ValueError(f"当前文件夹有多个 CSV，请用 --roster 指定队员名单：{names}")
    return candidates[0].resolve()


def read_roster(roster_path: Path) -> list[Player]:
    with roster_path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    players: list[Player] = []
    for row in rows:
        player_id = str(row.get("player_id") or "").strip()
        display_name = str(row.get("display_name") or "").strip()
        if not player_id or not display_name:
            continue
        players.append(
            Player(
                player_id=player_id,
                display_name=display_name,
                team_id=str(row.get("team_id") or "").strip(),
                team_name=str(row.get("team_name") or "").strip(),
                appearances=str(row.get("appearances") or row.get("games_played") or "").strip(),
                photo=str(row.get("photo") or "").strip(),
            )
        )
    if not players:
        raise ValueError("队员名单 CSV 里没有可用的 player_id / display_name。")
    return players


def build_players_api_url(site_url: str) -> str:
    parsed = urlparse(site_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"网站地址无效：{site_url}")
    path = parsed.path.rstrip("/")
    if path.endswith("/api/players"):
        return site_url.rstrip("/")
    return site_url.rstrip("/") + "/api/players"


def fetch_json(url: str, params: dict[str, object]) -> dict[str, object]:
    request_url = f"{url}?{urlencode(params)}"
    request = Request(
        request_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "werewolf-stats-player-photo-matcher/1.3.1",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise ValueError(f"读取线上名单失败：HTTP {exc.code}") from exc
    except URLError as exc:
        raise ValueError(f"读取线上名单失败：{exc.reason}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("网站返回的选手名单不是有效 JSON。") from exc
    if not isinstance(payload, dict):
        raise ValueError("网站返回的选手名单格式不正确。")
    return payload


def list_api_seasons(
    api_url: str,
    competition_name: str,
    fetcher: Callable[[str, dict[str, object]], dict[str, object]] = fetch_json,
) -> list[str]:
    payload = fetcher(
        api_url,
        {
            "competition": competition_name,
            "limit": 1,
            "offset": 0,
        },
    )
    filters = (
        payload.get("scope", {}).get("filters", {})
        if isinstance(payload.get("scope"), dict)
        else {}
    )
    options = filters.get("seasons", []) if isinstance(filters, dict) else []
    return [
        str(option.get("label") or "").strip()
        for option in options
        if isinstance(option, dict) and str(option.get("label") or "").strip()
    ]


def resolve_api_season(requested_season: str, available_seasons: list[str]) -> str:
    requested = requested_season.strip()
    if not requested:
        raise ValueError("请通过 --season 指定赛季。")
    exact = [
        season
        for season in available_seasons
        if unicodedata.normalize("NFKC", season).casefold()
        == unicodedata.normalize("NFKC", requested).casefold()
    ]
    if len(exact) == 1:
        return exact[0]

    requested_key = normalize_key(requested)
    suffix_matches = [
        season for season in available_seasons if normalize_key(season).endswith(requested_key)
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    if not available_seasons:
        raise ValueError("线上没有找到该赛事的赛季，请检查赛事名称。")
    if len(suffix_matches) > 1:
        raise ValueError(
            f"“{requested_season}”匹配到多个赛季：{'、'.join(suffix_matches)}，请填写完整赛季名。"
        )
    raise ValueError(
        f"线上没有找到赛季“{requested_season}”。可选赛季：{'、'.join(available_seasons)}"
    )


def read_roster_from_site(
    site_url: str,
    competition_name: str,
    requested_season: str,
    fetcher: Callable[[str, dict[str, object]], dict[str, object]] = fetch_json,
) -> tuple[list[Player], str]:
    if not competition_name.strip():
        raise ValueError("使用 --from-site 时必须通过 --competition 指定赛事名称。")
    api_url = build_players_api_url(site_url)
    available_seasons = list_api_seasons(api_url, competition_name, fetcher)
    season_name = resolve_api_season(requested_season, available_seasons)

    players_by_id: dict[str, Player] = {}
    offset = 0
    while True:
        payload = fetcher(
            api_url,
            {
                "competition": competition_name,
                "season": season_name,
                "limit": DEFAULT_API_LIMIT,
                "offset": offset,
            },
        )
        if payload.get("requires_scope"):
            raise ValueError("网站没有识别到指定赛事赛季，请检查赛事名称和赛季。")
        rows = payload.get("players")
        if not isinstance(rows, list):
            raise ValueError("网站返回的选手名单缺少 players 字段。")
        for row in rows:
            if not isinstance(row, dict):
                continue
            player_id = str(row.get("player_id") or "").strip()
            display_name = str(row.get("display_name") or "").strip()
            if not player_id or not display_name:
                continue
            players_by_id[player_id] = Player(
                player_id=player_id,
                display_name=display_name,
                team_name=str(row.get("team_name") or "").strip(),
                appearances=str(row.get("games_played") or "").strip(),
                photo=str(row.get("photo") or "").strip(),
            )
        pagination = payload.get("pagination")
        if not isinstance(pagination, dict) or not pagination.get("has_more"):
            break
        next_offset = int(pagination.get("offset") or offset) + int(
            pagination.get("limit") or DEFAULT_API_LIMIT
        )
        if next_offset <= offset:
            raise ValueError("网站选手名单分页异常，已停止读取。")
        offset = next_offset

    players = sorted(
        players_by_id.values(),
        key=lambda player: (player.display_name.casefold(), player.player_id),
    )
    if not players:
        raise ValueError("该赛事赛季没有可匹配的已出场选手。")
    return players, season_name


def list_photo_files(
    folder: Path,
    excluded_paths: set[Path],
    recursive: bool = True,
) -> list[Path]:
    folder = folder.resolve()
    excluded_paths = {path.resolve() for path in excluded_paths}
    iterator = folder.rglob("*") if recursive else folder.iterdir()
    photos: list[Path] = []
    for path in iterator:
        if not path.is_file() or path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
            continue
        if any(part.startswith(".") for part in path.relative_to(folder).parts):
            continue
        if path.resolve() in excluded_paths:
            continue
        photos.append(path.resolve())
    return sorted(photos, key=lambda item: str(item.relative_to(folder)).casefold())


def validate_photo_file(path: Path) -> str:
    try:
        size = path.stat().st_size
        if size <= 0:
            return "图片文件为空"
        with path.open("rb") as file:
            header = file.read(12)
    except OSError as exc:
        return f"图片无法读取：{exc}"

    extension = path.suffix.lower()
    if extension == ".webp":
        if len(header) < 12 or not header.startswith(b"RIFF") or header[8:12] != b"WEBP":
            return "图片内容与 WEBP 扩展名不一致"
        return ""
    signatures = IMAGE_SIGNATURES.get(extension, ())
    if signatures and not any(header.startswith(signature) for signature in signatures):
        return "图片内容与文件扩展名不一致"
    return ""


def build_candidate_scores(path: Path, folder: Path, players: list[Player]) -> dict[Player, tuple[int, str]]:
    variants = filename_variants(path)
    raw_stem_key = normalize_key(path.stem)
    relative_parent_key = normalize_key(str(path.relative_to(folder).parent))
    candidate_scores: dict[Player, tuple[int, str]] = {}

    for player in players:
        player_id_key = normalize_key(player.player_id)
        name_key = normalize_key(player.display_name)
        team_key = normalize_key(player.team_name)
        score = 0
        method = ""

        if raw_stem_key == player_id_key:
            score, method = 120, "选手 ID 完全匹配"
        elif name_key and raw_stem_key == name_key:
            score, method = 110, "选手名完全匹配"
        elif team_key and raw_stem_key in {team_key + name_key, name_key + team_key}:
            score, method = 105, "战队名与选手名组合匹配"
        elif name_key and name_key in variants:
            score, method = 100, "文件名分段/去除头像字样后匹配"

        if not score:
            continue
        if team_key and (
            team_key in raw_stem_key
            or team_key in relative_parent_key
        ):
            score += 5
            method += "，并匹配战队"
        candidate_scores[player] = (score, method)
    return candidate_scores


def suggest_player(path: Path, players: list[Player]) -> str:
    source_key = normalize_key(COPY_SUFFIX_PATTERN.sub("", path.stem))
    if len(source_key) < 2:
        return ""
    names_by_key: dict[str, list[Player]] = defaultdict(list)
    for player in players:
        key = normalize_key(player.display_name)
        if key:
            names_by_key[key].append(player)
    matches = difflib.get_close_matches(source_key, list(names_by_key), n=1, cutoff=0.72)
    if not matches:
        return ""
    candidates = names_by_key[matches[0]]
    if len(candidates) != 1:
        return ""
    player = candidates[0]
    return f"{player.display_name}（{player.team_name or '未分队'} / {player.player_id}）"


def match_photos(folder: Path, photos: list[Path], players: list[Player]) -> list[PhotoMatch]:
    folder = folder.resolve()
    provisional: list[PhotoMatch] = []
    for path in photos:
        validation_error = validate_photo_file(path)
        if validation_error:
            provisional.append(
                PhotoMatch(
                    path=path,
                    player=None,
                    status="invalid",
                    reason=validation_error,
                )
            )
            continue
        scores = build_candidate_scores(path, folder, players)
        if not scores:
            provisional.append(
                PhotoMatch(
                    path=path,
                    player=None,
                    status="unmatched",
                    reason="文件名未匹配到赛季现有选手",
                    suggestion=suggest_player(path, players),
                )
            )
            continue
        best_score = max(score for score, _method in scores.values())
        best_players = [
            player for player, (score, _method) in scores.items() if score == best_score
        ]
        if len(best_players) != 1:
            labels = "、".join(
                f"{player.display_name}（{player.team_name or '未分队'} / {player.player_id}）"
                for player in best_players
            )
            provisional.append(
                PhotoMatch(
                    path=path,
                    player=None,
                    status="ambiguous",
                    reason=f"文件名同时匹配多个同名选手：{labels}",
                )
            )
            continue
        player = best_players[0]
        provisional.append(
            PhotoMatch(
                path=path,
                player=player,
                status="included",
                method=scores[player][1],
            )
        )

    matches_by_player_id: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(provisional):
        if item.status == "included" and item.player:
            matches_by_player_id[item.player.player_id].append(index)
    for indexes in matches_by_player_id.values():
        if len(indexes) <= 1:
            continue
        source_names = "、".join(provisional[index].path.name for index in indexes)
        for index in indexes:
            item = provisional[index]
            provisional[index] = PhotoMatch(
                path=item.path,
                player=item.player,
                status="duplicate",
                method=item.method,
                reason=f"同一选手匹配到多张图片，需保留其中一张：{source_names}",
            )
    return provisional


def load_manual_selections(selection_path: str) -> ManualSelections:
    if not selection_path:
        return ManualSelections(assignments={})
    path = Path(selection_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"人工选择文件不存在：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"人工选择文件无法读取：{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("人工选择文件格式不正确。")

    if "assignments" not in payload and "rejected_sources" not in payload:
        assignments_payload = payload
        rejected_payload: object = []
    else:
        version = payload.get("version", 2)
        if version != 2:
            raise ValueError(f"不支持的人工选择文件版本：{version}")
        assignments_payload = payload.get("assignments", {})
        rejected_payload = payload.get("rejected_sources", [])

    if not isinstance(assignments_payload, dict) or not isinstance(rejected_payload, list):
        raise ValueError("人工选择文件格式不正确，assignments 应为对象，rejected_sources 应为数组。")
    assignments = {
        str(player_id).strip(): str(source_file).strip()
        for player_id, source_file in assignments_payload.items()
        if str(player_id).strip() and str(source_file).strip()
    }
    rejected_sources = frozenset(
        str(source_file).strip()
        for source_file in rejected_payload
        if str(source_file).strip()
    )
    return ManualSelections(
        assignments=assignments,
        rejected_sources=rejected_sources,
    )


def normalize_manual_selections(
    selections: ManualSelections | dict[str, str],
) -> ManualSelections:
    if isinstance(selections, ManualSelections):
        return selections
    return ManualSelections(
        assignments={
            str(player_id).strip(): str(source_file).strip()
            for player_id, source_file in selections.items()
            if str(player_id).strip() and str(source_file).strip()
        }
    )


def apply_manual_selections(
    folder: Path,
    matches: list[PhotoMatch],
    selections: ManualSelections | dict[str, str],
    players: list[Player] | None = None,
) -> tuple[list[PhotoMatch], int]:
    selection_config = normalize_manual_selections(selections)
    assignments = selection_config.assignments
    rejected_sources = set(selection_config.rejected_sources)
    if not assignments and not rejected_sources:
        return matches, 0
    folder = folder.resolve()
    source_indexes = {
        str(item.path.relative_to(folder)): index
        for index, item in enumerate(matches)
    }
    roster_players = players or [
        item.player for item in matches if item.player is not None
    ]
    players_by_id = {player.player_id: player for player in roster_players}

    unknown_players = sorted(set(assignments) - set(players_by_id))
    if unknown_players:
        raise ValueError(f"人工选择包含当前赛季不存在的选手：{'、'.join(unknown_players)}")
    unknown_sources = sorted(
        (set(assignments.values()) | rejected_sources) - set(source_indexes)
    )
    if unknown_sources:
        raise ValueError(f"人工选择包含不存在的图片：{'、'.join(unknown_sources)}")
    duplicate_sources = sorted(
        source
        for source, count in Counter(assignments.values()).items()
        if count > 1
    )
    if duplicate_sources:
        raise ValueError(f"同一图片不能分配给多位选手：{'、'.join(duplicate_sources)}")
    assigned_sources = set(assignments.values())
    rejected_assignments = sorted(assigned_sources & rejected_sources)
    if rejected_assignments:
        raise ValueError(f"图片不能同时分配并标记为不导入：{'、'.join(rejected_assignments)}")
    invalid_sources = sorted(
        source
        for source in assigned_sources
        if matches[source_indexes[source]].status == "invalid"
    )
    if invalid_sources:
        raise ValueError(f"无效图片不能分配给选手：{'、'.join(invalid_sources)}")

    player_by_selected_source = {
        source: players_by_id[player_id]
        for player_id, source in assignments.items()
    }
    resolved: list[PhotoMatch] = []
    for item in matches:
        source = str(item.path.relative_to(folder))
        if source in rejected_sources:
            resolved.append(
                PhotoMatch(
                    path=item.path,
                    player=item.player,
                    status="rejected",
                    method=item.method,
                    reason="App 内人工标记为不导入",
                )
            )
            continue
        selected_player = player_by_selected_source.get(source)
        if selected_player:
            resolved.append(
                PhotoMatch(
                    path=item.path,
                    player=selected_player,
                    status="included",
                    method="App 内人工指定",
                )
            )
            continue
        if item.player and item.player.player_id in assignments:
            resolved.append(
                PhotoMatch(
                    path=item.path,
                    player=item.player,
                    status="rejected",
                    method=item.method,
                    reason="该选手已人工指定其他头像",
                )
            )
            continue
        resolved.append(item)

    candidate_indexes_by_player: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(resolved):
        if item.status in {"included", "duplicate"} and item.player:
            candidate_indexes_by_player[item.player.player_id].append(index)
    for player_id, indexes in candidate_indexes_by_player.items():
        if player_id in assignments:
            continue
        if len(indexes) == 1:
            index = indexes[0]
            item = resolved[index]
            if item.status == "duplicate":
                resolved[index] = PhotoMatch(
                    path=item.path,
                    player=item.player,
                    status="included",
                    method=item.method,
                )
            continue
        source_names = "、".join(resolved[index].path.name for index in indexes)
        for index in indexes:
            item = resolved[index]
            resolved[index] = PhotoMatch(
                path=item.path,
                player=item.player,
                status="duplicate",
                method=item.method,
                reason=f"同一选手匹配到多张图片，需保留其中一张：{source_names}",
            )
    return resolved, len(assignments) + len(rejected_sources)


def count_review_groups(matches: list[PhotoMatch]) -> int:
    duplicate_player_ids = {
        item.player.player_id
        for item in matches
        if item.status == "duplicate" and item.player
    }
    ambiguous_count = sum(item.status == "ambiguous" for item in matches)
    return len(duplicate_player_ids) + ambiguous_count


def report_rows(
    folder: Path,
    matches: list[PhotoMatch],
    players: list[Player],
    scope_label: str = "",
    compression_results: dict[Path, CompressionResult] | None = None,
) -> list[dict[str, str]]:
    compression_results = compression_results or {}
    rows: list[dict[str, str]] = []
    matched_player_ids = {
        item.player.player_id
        for item in matches
        if item.status == "included" and item.player
    }
    for item in matches:
        compression = compression_results.get(item.path)
        rows.append(
            {
                "scope": scope_label,
                "status": item.status,
                "source_file": str(item.path.relative_to(folder)),
                "matched_player_id": item.player.player_id if item.player else "",
                "display_name": item.player.display_name if item.player else "",
                "team_name": item.player.team_name if item.player else "",
                "match_method": item.method,
                "reason": item.reason,
                "suggestion": item.suggestion,
                "compression_note": compression.note if compression else "",
                "output_file": (
                    f"{item.player.player_id}{compression.output_extension}"
                    if compression and item.player
                    else (
                        f"{item.player.player_id}{item.path.suffix.lower()}"
                        if item.status == "included" and item.player
                        else ""
                    )
                ),
            }
        )
    for player in players:
        if player.player_id in matched_player_ids:
            continue
        rows.append(
            {
                "scope": scope_label,
                "status": "missing",
                "source_file": "",
                "matched_player_id": player.player_id,
                "display_name": player.display_name,
                "team_name": player.team_name,
                "match_method": "",
                "reason": "赛季选手未找到可自动收录的唯一头像",
                "suggestion": "",
                "compression_note": "",
                "output_file": "",
            }
        )
    return rows


def compress_photo_for_upload(
    path: Path,
    target_bytes: int = COMPRESSED_TARGET_BYTES,
) -> tuple[bytes, str, CompressionResult]:
    if Image is None or ImageOps is None:
        raise ValueError("图片需要自动压缩，但当前匹配组件缺少压缩能力，请重新构建 App。")
    original_bytes = path.stat().st_size
    target_bytes = min(
        max(int(target_bytes), MIN_COMPRESSED_TARGET_BYTES),
        COMPRESSED_TARGET_BYTES,
    )
    try:
        with Image.open(path) as source:
            if getattr(source, "is_animated", False):
                source.seek(0)
            prepared = ImageOps.exif_transpose(source)
            if prepared.mode in {"RGBA", "LA"} or (
                prepared.mode == "P" and "transparency" in prepared.info
            ):
                rgba = prepared.convert("RGBA")
                flattened = Image.new("RGB", rgba.size, "white")
                flattened.paste(rgba, mask=rgba.getchannel("A"))
                prepared = flattened
            else:
                prepared = prepared.convert("RGB")

            longest_edge = max(prepared.size)
            dimension_limits = [
                limit
                for limit in (COMPRESSED_MAX_DIMENSION, 2000, 1600, 1280, 1024, 800, 640)
                if limit < longest_edge
            ]
            dimension_limits.insert(0, min(longest_edge, COMPRESSED_MAX_DIMENSION))
            dimension_limits = list(dict.fromkeys(dimension_limits))
            for dimension_limit in dimension_limits:
                candidate = prepared.copy()
                candidate.thumbnail(
                    (dimension_limit, dimension_limit),
                    Image.Resampling.LANCZOS,
                )
                for quality in (88, 82, 76, 70, 64, 58, 52, 46, 40):
                    buffer = BytesIO()
                    candidate.save(
                        buffer,
                        format="JPEG",
                        quality=quality,
                        optimize=True,
                        progressive=True,
                    )
                    payload = buffer.getvalue()
                    if len(payload) <= target_bytes:
                        return payload, ".jpg", CompressionResult(
                            original_bytes=original_bytes,
                            output_bytes=len(payload),
                            output_extension=".jpg",
                        )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"{path.name} 自动压缩失败：{exc}") from exc
    raise ValueError(f"{path.name} 自动压缩后仍超过网站限制，请手动缩小图片。")


def write_zip(
    output_zip: Path,
    matches: list[PhotoMatch],
    compression_results: dict[Path, CompressionResult] | None = None,
    compressor: Callable[[Path, int], tuple[bytes, str, CompressionResult]] = compress_photo_for_upload,
    archive_payload_budget_bytes: int = ZIP_PAYLOAD_BUDGET_BYTES,
    archive_target_bytes: int = MAX_OUTPUT_ZIP_BYTES,
) -> int:
    included = [item for item in matches if item.status == "included" and item.player]
    captured_results = compression_results if compression_results is not None else {}
    source_bytes = sum(item.path.stat().st_size for item in included)
    reduce_for_archive = source_bytes > archive_payload_budget_bytes
    per_photo_target = COMPRESSED_TARGET_BYTES
    if reduce_for_archive and included:
        zip_overhead_reserve = len(included) * 2048
        per_photo_target = max(
            MIN_COMPRESSED_TARGET_BYTES,
            (archive_payload_budget_bytes - zip_overhead_reserve) // len(included),
        )
        per_photo_target = min(per_photo_target, COMPRESSED_TARGET_BYTES)
    temporary_zip = output_zip.with_name(f".{output_zip.name}.tmp")
    temporary_zip.unlink(missing_ok=True)
    try:
        with ZipFile(temporary_zip, "w", compression=ZIP_DEFLATED) as output:
            for item in included:
                source_size = item.path.stat().st_size
                should_compress = source_size > MAX_UPLOAD_BYTES or (
                    reduce_for_archive and source_size > per_photo_target
                )
                if should_compress:
                    payload, extension, result = compressor(
                        item.path,
                        min(per_photo_target, COMPRESSED_TARGET_BYTES),
                    )
                    if not payload or len(payload) > MAX_UPLOAD_BYTES:
                        raise ValueError(f"{item.path.name} 自动压缩后仍超过网站单张 5 MB 限制。")
                    output_name = f"{item.player.player_id}{extension}"
                    output.writestr(output_name, payload)
                    captured_results[item.path] = result
                else:
                    output_name = f"{item.player.player_id}{item.path.suffix.lower()}"
                    output.write(item.path, output_name)
        if temporary_zip.stat().st_size > archive_target_bytes:
            raise ValueError(
                f"头像 ZIP 生成后仍有 {temporary_zip.stat().st_size / 1024 / 1024:.1f} MB，"
                f"超过 {archive_target_bytes / 1024 / 1024:.0f} MB 安全上传上限。"
            )
        temporary_zip.replace(output_zip)
    except Exception:
        temporary_zip.unlink(missing_ok=True)
        raise
    return len(included)


def write_csv_report(report_path: Path, rows: list[dict[str, str]]) -> None:
    with report_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "scope",
                "status",
                "source_file",
                "matched_player_id",
                "display_name",
                "team_name",
                "match_method",
                "reason",
                "suggestion",
                "compression_note",
                "output_file",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_json_report(
    report_path: Path,
    rows: list[dict[str, str]],
    scope_label: str,
    players: list[Player],
    matches: list[PhotoMatch],
    compression_results: dict[Path, CompressionResult] | None = None,
) -> None:
    compression_results = compression_results or {}
    counts = Counter(item.status for item in matches)
    payload = {
        "scope_label": scope_label,
        "player_count": len(players),
        "players": [
            {
                "player_id": player.player_id,
                "display_name": player.display_name,
                "team_id": player.team_id,
                "team_name": player.team_name,
                "appearances": player.appearances,
                "photo": player.photo,
            }
            for player in players
        ],
        "summary": {
            "scanned_count": len(matches),
            "included_count": counts["included"],
            "review_group_count": count_review_groups(matches),
            "invalid_count": counts["invalid"],
            "unmatched_count": counts["unmatched"],
            "compressed_count": len(compression_results),
        },
        "rows": rows,
    }
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_html_report(
    report_path: Path,
    folder: Path,
    matches: list[PhotoMatch],
    players: list[Player],
    scope_label: str,
    compression_results: dict[Path, CompressionResult] | None = None,
) -> None:
    compression_results = compression_results or {}
    status_labels = {
        "included": "已收录",
        "duplicate": "同一选手多图",
        "ambiguous": "同名歧义",
        "rejected": "人工确认未选用",
        "unmatched": "未匹配",
        "invalid": "图片无效",
        "missing": "缺少头像",
    }
    status_counts = Counter(item.status for item in matches)
    included_ids = {
        item.player.player_id
        for item in matches
        if item.status == "included" and item.player
    }
    missing_players = [player for player in players if player.player_id not in included_ids]

    cards: list[str] = []
    for item in matches:
        relative_name = str(item.path.relative_to(folder))
        player_label = (
            f"{item.player.display_name} · {item.player.team_name or '未分队'} · {item.player.player_id}"
            if item.player
            else "未确定选手"
        )
        detail = item.reason or item.method
        if item.suggestion:
            detail += f"；可能是：{item.suggestion}"
        compression = compression_results.get(item.path)
        if compression:
            detail += f"；{compression.note}"
        cards.append(
            f"""
            <article class="card status-{html.escape(item.status)}">
              <img src="{html.escape(item.path.as_uri())}" alt="{html.escape(relative_name)}">
              <div class="content">
                <span class="badge">{html.escape(status_labels[item.status])}</span>
                <h3>{html.escape(relative_name)}</h3>
                <p>{html.escape(player_label)}</p>
                <small>{html.escape(detail)}</small>
              </div>
            </article>
            """
        )
    for player in missing_players:
        cards.append(
            f"""
            <article class="card status-missing">
              <div class="placeholder">?</div>
              <div class="content">
                <span class="badge">缺少头像</span>
                <h3>{html.escape(player.display_name)}</h3>
                <p>{html.escape(player.team_name or '未分队')} · {html.escape(player.player_id)}</p>
                <small>没有找到可自动收录的唯一图片。</small>
              </div>
            </article>
            """
        )

    report_path.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>选手头像匹配预览</title>
  <style>
    :root {{ color-scheme: dark; --gold:#d7ae5a; --panel:#171717; --muted:#aaa; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:#090909; color:#f5f1e8; font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    main {{ width:min(1400px,94vw); margin:36px auto 80px; }}
    h1 {{ margin:0 0 8px; font-size:30px; }}
    .scope {{ color:var(--gold); }}
    .summary {{ display:flex; flex-wrap:wrap; gap:12px; margin:24px 0; }}
    .metric {{ min-width:130px; padding:14px 18px; background:var(--panel); border:1px solid #303030; border-radius:12px; }}
    .metric b {{ display:block; font-size:25px; color:var(--gold); }}
    .hint {{ padding:14px 18px; border-left:3px solid var(--gold); background:#17140e; color:#ddd; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:14px; margin-top:24px; }}
    .card {{ overflow:hidden; border:1px solid #303030; border-radius:12px; background:var(--panel); }}
    .card img,.placeholder {{ width:100%; height:190px; object-fit:cover; background:#222; }}
    .placeholder {{ display:grid; place-items:center; font-size:56px; color:#555; }}
    .content {{ padding:14px; }}
    .content h3 {{ margin:9px 0 5px; font-size:15px; word-break:break-all; }}
    .content p {{ margin:0 0 7px; color:#ddd; }}
    .content small {{ color:var(--muted); }}
    .badge {{ display:inline-block; padding:3px 8px; border-radius:999px; font-size:12px; background:#333; }}
    .status-included {{ border-color:#496b42; }}
    .status-included .badge {{ background:#244522; color:#b9e4af; }}
    .status-duplicate,.status-ambiguous {{ border-color:#8b6728; }}
    .status-duplicate .badge,.status-ambiguous .badge {{ background:#4d3515; color:#f2ce86; }}
    .status-rejected {{ opacity:.58; }}
    .status-rejected .badge {{ background:#303030; color:#bbb; }}
    .status-invalid {{ border-color:#8b3434; }}
    .status-invalid .badge {{ background:#4b2020; color:#f1aaaa; }}
    .status-unmatched,.status-missing {{ opacity:.78; }}
  </style>
</head>
<body>
<main>
  <h1>选手头像匹配预览</h1>
  <div class="scope">{html.escape(scope_label)}</div>
  <div class="summary">
    <div class="metric"><b>{len(players)}</b>名单选手</div>
    <div class="metric"><b>{len(matches)}</b>扫描图片</div>
    <div class="metric"><b>{status_counts['included']}</b>最终收录</div>
    <div class="metric"><b>{len(compression_results)}</b>自动压缩</div>
    <div class="metric"><b>{count_review_groups(matches)}</b>组需要确认</div>
    <div class="metric"><b>{status_counts['unmatched']}</b>无关/未匹配</div>
    <div class="metric"><b>{len(missing_players)}</b>仍缺头像</div>
  </div>
  <p class="hint">只有绿色“已收录”项目会进入 ZIP。Mac App 可为任意有效图片更换选手或标记为不导入。</p>
  <section class="grid">{''.join(cards)}</section>
</main>
</body>
</html>
""",
        encoding="utf-8",
    )


def resolve_output_path(folder: Path, value: str, default_name: str) -> Path:
    path = Path(value or default_name).expanduser()
    return path.resolve() if path.is_absolute() else (folder / path).resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "从包含子文件夹的图片目录中筛选指定赛事赛季选手头像，并生成后台可直接上传的 ZIP。"
        )
    )
    parser.add_argument(
        "--folder",
        default="",
        help="待扫描的图片文件夹；默认使用脚本所在文件夹。",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--roster", default="", help="后台导出的赛季队员名单 CSV。")
    source.add_argument(
        "--from-site",
        action="store_true",
        help="直接从线上公开选手接口读取名单。",
    )
    parser.add_argument(
        "--site-url",
        default=DEFAULT_SITE_URL,
        help=f"网站地址；默认 {DEFAULT_SITE_URL}。",
    )
    parser.add_argument("--competition", default="", help="线上赛事完整名称。")
    parser.add_argument("--season", default="", help="赛季名，支持 S2 这样的唯一后缀。")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_ZIP, help="输出 ZIP 文件名或路径。")
    parser.add_argument("--report", default=DEFAULT_REPORT_CSV, help="输出 CSV 核对表。")
    parser.add_argument(
        "--report-json",
        default=DEFAULT_REPORT_JSON,
        help="输出供 Mac App 读取的 JSON 核对表。",
    )
    parser.add_argument(
        "--preview",
        default=DEFAULT_REPORT_HTML,
        help="输出可浏览图片的 HTML 预览报告。",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="只扫描文件夹第一层，不扫描子文件夹。",
    )
    parser.add_argument(
        "--selections",
        default="",
        help="Mac App 生成的人工选择 JSON 文件。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    folder = (
        Path(args.folder).expanduser().resolve()
        if args.folder
        else Path(__file__).resolve().parent
    )
    if not folder.is_dir():
        print(f"文件夹不存在：{folder}", file=sys.stderr)
        return 1

    output_zip = resolve_output_path(folder, args.output, DEFAULT_OUTPUT_ZIP)
    report_path = resolve_output_path(folder, args.report, DEFAULT_REPORT_CSV)
    report_json_path = resolve_output_path(folder, args.report_json, DEFAULT_REPORT_JSON)
    preview_path = resolve_output_path(folder, args.preview, DEFAULT_REPORT_HTML)
    for parent in {
        output_zip.parent,
        report_path.parent,
        report_json_path.parent,
        preview_path.parent,
    }:
        parent.mkdir(parents=True, exist_ok=True)

    try:
        if args.from_site:
            players, resolved_season = read_roster_from_site(
                args.site_url,
                args.competition,
                args.season,
            )
            scope_label = f"{args.competition} / {resolved_season}（线上名单）"
            roster_label = f"{args.site_url.rstrip('/')}/api/players"
        else:
            roster_path = find_roster_csv(folder, args.roster)
            players = read_roster(roster_path)
            scope_label = f"{roster_path.name}（导出名单）"
            roster_label = str(roster_path)

        photos = list_photo_files(
            folder,
            {output_zip, report_path, report_json_path, preview_path},
            recursive=not args.no_recursive,
        )
        matches = match_photos(folder, photos, players)
        selections = load_manual_selections(args.selections)
        matches, confirmed_count = apply_manual_selections(
            folder,
            matches,
            selections,
            players,
        )
        compression_results: dict[Path, CompressionResult] = {}
        written_count = write_zip(output_zip, matches, compression_results)
        rows = report_rows(
            folder,
            matches,
            players,
            scope_label,
            compression_results,
        )
        write_csv_report(report_path, rows)
        write_json_report(
            report_json_path,
            rows,
            scope_label,
            players,
            matches,
            compression_results,
        )
        write_html_report(
            preview_path,
            folder,
            matches,
            players,
            scope_label,
            compression_results,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"文件处理失败：{exc}", file=sys.stderr)
        return 1

    counts = Counter(item.status for item in matches)
    print(f"队员名单：{roster_label}")
    print(f"赛季范围：{scope_label}")
    print(f"名单选手：{len(players)} 位")
    print(f"扫描图片：{len(photos)} 张")
    print(f"最终收录：{written_count} 张")
    print(f"自动压缩：{len(compression_results)} 张")
    print(f"人工处理：{confirmed_count} 项")
    print(f"需要确认：{count_review_groups(matches)} 组")
    print(f"无效图片：{counts['invalid']} 张")
    print(f"未匹配跳过：{counts['unmatched']} 张")
    print(f"已生成 ZIP：{output_zip}")
    print(f"CSV 核对表：{report_path}")
    print(f"JSON 核对表：{report_json_path}")
    print(f"图片预览：{preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
