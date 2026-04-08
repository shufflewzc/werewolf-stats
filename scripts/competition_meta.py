from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from zoneinfo import ZoneInfo

from generate_stats import (
    get_match_competition_name,
    list_competitions,
    list_seasons as stats_list_seasons,
)
from sqlite_store import load_meta_value, save_meta_value


CHINA_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_REGION_NAME = "广州"
SERIES_CATALOG_META_KEY = "series_catalog"
SEASON_CATALOG_META_KEY = "season_catalog"
REGION_NAME_CANDIDATES = (
    "广州",
    "北京",
    "上海",
    "深圳",
    "杭州",
    "成都",
    "武汉",
    "天津",
    "南京",
    "西安",
    "重庆",
    "苏州",
    "长沙",
    "青岛",
    "福州",
    "厦门",
    "全国",
)
COMPETITION_CODE_SUFFIXES = (
    "公开赛",
    "联赛",
    "系列赛",
    "总决赛",
    "季后赛",
    "常规赛",
    "表演赛",
    "邀请赛",
)
CHINESE_INITIAL_MAP = {
    "北": "b",
    "京": "j",
    "城": "c",
    "上": "s",
    "海": "h",
    "广": "g",
    "州": "z",
    "深": "s",
    "圳": "z",
    "杭": "h",
    "成": "c",
    "都": "d",
    "武": "w",
    "汉": "h",
    "天": "t",
    "津": "j",
    "南": "n",
    "宁": "n",
    "西": "x",
    "安": "a",
    "重": "c",
    "庆": "q",
    "苏": "s",
    "长": "c",
    "沙": "s",
    "青": "q",
    "岛": "d",
    "福": "f",
    "厦": "x",
    "门": "m",
    "大": "d",
    "师": "s",
    "冠": "g",
    "军": "j",
    "杯": "b",
    "邀": "y",
    "请": "q",
    "春": "c",
    "季": "j",
    "夏": "x",
    "秋": "q",
    "冬": "d",
    "市": "s",
    "区": "q",
    "国": "g",
    "际": "j",
    "站": "z",
    "华": "h",
    "中": "z",
    "东": "d",
}

_SERIES_CACHE_KEY: tuple[str, tuple[str, ...]] | None = None
_SERIES_CACHE_VALUE: list[dict[str, Any]] | None = None
_SEASON_CACHE_KEY: tuple[str, tuple[tuple[str, tuple[str, ...]], ...], tuple[str, ...]] | None = None
_SEASON_CACHE_VALUE: list[dict[str, Any]] | None = None


def china_now() -> datetime:
    return datetime.now(CHINA_TZ)


def china_today_label() -> str:
    return china_now().strftime("%Y-%m-%d")


def normalize_slug_fragment(value: str, fallback: str = "item") -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower())
    normalized = normalized.strip("-")
    return normalized or fallback


def compact_region_name(region_name: str) -> str:
    return re.sub(r"(市|地区|盟|自治州)$", "", region_name.strip())


def parse_china_datetime(value: str) -> datetime | None:
    normalized = value.strip()
    if not normalized:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(normalized, fmt)
            return parsed.replace(tzinfo=CHINA_TZ)
        except ValueError:
            continue
    return None


def normalize_datetime_local_value(value: str) -> str:
    parsed = parse_china_datetime(value)
    if not parsed:
        return ""
    return parsed.strftime("%Y-%m-%dT%H:%M")


def format_datetime_local_label(value: str) -> str:
    parsed = parse_china_datetime(value)
    if not parsed:
        return "未设置"
    return parsed.strftime("%Y-%m-%d %H:%M")


def build_competition_code(competition_name: str) -> str:
    ascii_tokens = re.findall(r"[A-Za-z0-9]+", competition_name)
    if ascii_tokens:
        return "".join(ascii_tokens).lower()[:12]

    trimmed_name = competition_name.strip()
    for suffix in COMPETITION_CODE_SUFFIXES:
        trimmed_name = trimmed_name.replace(suffix, "")

    initials = "".join(CHINESE_INITIAL_MAP.get(char, "") for char in trimmed_name)
    initials = re.sub(r"(.)\1+", r"\1", initials)
    return initials[:6] or "event"


def infer_region_name_from_competition(competition_name: str) -> str:
    normalized_name = competition_name.strip()
    for region_name in REGION_NAME_CANDIDATES:
        if region_name in normalized_name:
            return region_name
    return DEFAULT_REGION_NAME if DEFAULT_REGION_NAME in normalized_name else "全国"


def infer_series_name_from_competition(
    competition_name: str,
    region_name: str | None = None,
) -> str:
    normalized_name = competition_name.strip()
    if region_name and region_name in normalized_name:
        prefix, _, _ = normalized_name.partition(region_name)
        if prefix.strip():
            return prefix.strip()

    trimmed_name = normalized_name
    for suffix in COMPETITION_CODE_SUFFIXES:
        if trimmed_name.endswith(suffix):
            trimmed_name = trimmed_name[: -len(suffix)].strip()
            break
    if region_name:
        trimmed_name = trimmed_name.replace(region_name, "").strip()
    return trimmed_name or normalized_name


def build_series_slug(series_name: str, series_code: str = "") -> str:
    seed = (series_code or "").strip() or build_competition_code(series_name)
    return normalize_slug_fragment(seed, "series")


def build_city_code(competition_name: str) -> str:
    region_name = compact_region_name(infer_region_name_from_competition(competition_name))
    ascii_tokens = re.findall(r"[A-Za-z0-9]+", region_name)
    if ascii_tokens:
        if len(ascii_tokens) == 1:
            return ascii_tokens[0].lower()[:6]
        return "".join(token[0] for token in ascii_tokens).lower()[:6]

    initials = "".join(CHINESE_INITIAL_MAP.get(char, "") for char in region_name)
    initials = re.sub(r"(.)\1+", r"\1", initials)
    return initials[:6] or "city"


def build_season_code(season_name: str) -> str:
    normalized_name = season_name.strip()
    ascii_tokens = re.findall(r"[A-Za-z0-9]+", normalized_name)
    if ascii_tokens:
        if len(ascii_tokens) == 1:
            token = re.sub(r"\d{4}", "", ascii_tokens[0]).lower()
            if token:
                return token[:8]
        token = "".join(part[0] for part in ascii_tokens if part).lower()
        token = re.sub(r"\d", "", token)
        if token:
            return token[:8]

    trimmed_name = re.sub(r"\d{4}", "", normalized_name)
    for suffix in ("联赛", "赛季", "公开赛", "系列赛", "常规赛", "季后赛", "总决赛"):
        trimmed_name = trimmed_name.replace(suffix, "")
    trimmed_name = trimmed_name.strip()
    initials = "".join(CHINESE_INITIAL_MAP.get(char, "") for char in trimmed_name)
    initials = re.sub(r"(.)\1+", r"\1", initials)
    return initials[:8] or "season"


def build_match_serial(
    competition_name: str,
    season_name: str,
    played_on: str,
    sequence: int,
) -> str:
    city_code = build_city_code(competition_name)
    season_code = build_season_code(season_name)
    date_code = re.sub(r"[^0-9]", "", played_on)[2:8]
    if len(date_code) != 6:
        date_code = "000000"
    return f"{city_code}-{season_code}-{date_code}-{sequence:02d}"


def canonicalize_match_ids(
    matches: list[dict[str, Any]],
    target_original_id: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    grouped_matches: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for match in matches:
        key = (
            build_city_code(get_match_competition_name(match)),
            build_season_code(str(match.get("season") or "")),
            str(match.get("played_on") or ""),
        )
        grouped_matches.setdefault(key, []).append(match)

    normalized_matches: list[dict[str, Any]] = []
    resolved_target_id = target_original_id
    for key in sorted(grouped_matches.keys()):
        scoped_matches = sorted(
            grouped_matches[key],
            key=lambda item: (
                item["round"],
                item["game_no"],
                str(item.get("table_label") or ""),
                item["match_id"],
            ),
        )
        for sequence, match in enumerate(scoped_matches, start=1):
            normalized_match = {
                **match,
                "match_id": build_match_serial(
                    get_match_competition_name(match),
                    str(match.get("season") or ""),
                    key[2],
                    sequence,
                ),
            }
            normalized_matches.append(normalized_match)
            if target_original_id and match["match_id"] == target_original_id:
                resolved_target_id = normalized_match["match_id"]

    normalized_matches.sort(
        key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"])
    )
    return normalized_matches, resolved_target_id


def normalize_series_catalog_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    competition_name = str(entry.get("competition_name") or "").strip()
    if not competition_name:
        return None

    region_name = str(entry.get("region_name") or "").strip() or infer_region_name_from_competition(
        competition_name
    )
    series_name = str(entry.get("series_name") or "").strip() or infer_series_name_from_competition(
        competition_name,
        region_name,
    )
    series_code = str(entry.get("series_code") or "").strip() or build_competition_code(
        series_name
    )
    summary = str(entry.get("summary") or "").strip()
    page_badge = str(entry.get("page_badge") or "").strip()
    hero_title = str(entry.get("hero_title") or "").strip()
    hero_intro = str(entry.get("hero_intro") or "").strip()
    hero_note = str(entry.get("hero_note") or "").strip()
    preserved_series_slug = str(entry.get("series_slug") or "").strip()

    return {
        "competition_name": competition_name,
        "region_name": region_name,
        "series_name": series_name,
        "series_code": series_code,
        "series_slug": preserved_series_slug or build_series_slug(series_name, series_code),
        "summary": summary,
        "page_badge": page_badge,
        "hero_title": hero_title,
        "hero_intro": hero_intro,
        "hero_note": hero_note,
        "active": bool(entry.get("active", True)),
        "created_by": str(entry.get("created_by") or "system").strip() or "system",
        "created_on": str(entry.get("created_on") or china_today_label()).strip()
        or china_today_label(),
    }


def _series_cache_signature(data: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    stored_value = load_meta_value(SERIES_CATALOG_META_KEY) or ""
    return stored_value, tuple(sorted(list_competitions(data)))


def load_series_catalog(data: dict[str, Any]) -> list[dict[str, Any]]:
    global _SERIES_CACHE_KEY, _SERIES_CACHE_VALUE
    cache_key = _series_cache_signature(data)
    if _SERIES_CACHE_KEY == cache_key and _SERIES_CACHE_VALUE is not None:
        return [dict(entry) for entry in _SERIES_CACHE_VALUE]

    raw_catalog: Any = []
    if cache_key[0]:
        try:
            raw_catalog = json.loads(cache_key[0])
        except json.JSONDecodeError:
            raw_catalog = []

    catalog_by_competition: dict[str, dict[str, Any]] = {}
    if isinstance(raw_catalog, list):
        for raw_entry in raw_catalog:
            if not isinstance(raw_entry, dict):
                continue
            entry = normalize_series_catalog_entry(raw_entry)
            if entry:
                catalog_by_competition[entry["competition_name"]] = entry

    for competition_name in list_competitions(data):
        if competition_name in catalog_by_competition:
            continue
        inferred_entry = normalize_series_catalog_entry(
            {
                "competition_name": competition_name,
                "region_name": infer_region_name_from_competition(competition_name),
                "series_name": infer_series_name_from_competition(
                    competition_name,
                    infer_region_name_from_competition(competition_name),
                ),
                "summary": "",
                "active": True,
                "created_by": "system",
                "created_on": china_today_label(),
            }
        )
        if inferred_entry:
            catalog_by_competition[competition_name] = inferred_entry

    sorted_catalog = sorted(
        catalog_by_competition.values(),
        key=lambda item: (
            item["region_name"] != DEFAULT_REGION_NAME,
            item["region_name"],
            item["series_name"],
            item["competition_name"],
        ),
    )
    _SERIES_CACHE_KEY = cache_key
    _SERIES_CACHE_VALUE = [dict(entry) for entry in sorted_catalog]
    return [dict(entry) for entry in sorted_catalog]


def save_series_catalog(catalog: list[dict[str, Any]]) -> None:
    global _SERIES_CACHE_KEY, _SERIES_CACHE_VALUE, _SEASON_CACHE_KEY, _SEASON_CACHE_VALUE
    normalized_catalog = [
        entry
        for entry in (
            normalize_series_catalog_entry(item) if isinstance(item, dict) else None
            for item in catalog
        )
        if entry
    ]
    save_meta_value(
        SERIES_CATALOG_META_KEY,
        json.dumps(normalized_catalog, ensure_ascii=False, indent=2),
    )
    _SERIES_CACHE_KEY = None
    _SERIES_CACHE_VALUE = None
    _SEASON_CACHE_KEY = None
    _SEASON_CACHE_VALUE = None


def get_series_entry_by_competition(
    catalog: list[dict[str, Any]],
    competition_name: str,
) -> dict[str, Any] | None:
    for entry in catalog:
        if entry["competition_name"] == competition_name:
            return entry
    return None


def get_series_entries_by_slug(
    catalog: list[dict[str, Any]],
    series_slug: str,
) -> list[dict[str, Any]]:
    return [entry for entry in catalog if entry["series_slug"] == series_slug]


def merge_team_ids(*team_groups: list[str]) -> list[str]:
    seen_team_ids: set[str] = set()
    merged_team_ids: list[str] = []
    for team_group in team_groups:
        for team_id in team_group:
            normalized_team_id = str(team_id).strip()
            if not normalized_team_id or normalized_team_id in seen_team_ids:
                continue
            seen_team_ids.add(normalized_team_id)
            merged_team_ids.append(normalized_team_id)
    return merged_team_ids


def build_series_context_from_competition(
    competition_name: str,
    catalog: list[dict[str, Any]],
) -> dict[str, str]:
    series_entry = get_series_entry_by_competition(catalog, competition_name)
    if series_entry:
        return {
            "series_slug": series_entry["series_slug"],
            "series_name": series_entry["series_name"],
            "series_code": series_entry["series_code"],
        }
    region_name = infer_region_name_from_competition(competition_name)
    series_name = infer_series_name_from_competition(competition_name, region_name)
    series_code = build_competition_code(series_name)
    return {
        "series_slug": build_series_slug(series_name, series_code),
        "series_name": series_name,
        "series_code": series_code,
    }


def get_season_status(entry: dict[str, Any], now: datetime | None = None) -> str:
    current = now or china_now()
    start_at = parse_china_datetime(str(entry.get("start_at") or ""))
    end_at = parse_china_datetime(str(entry.get("end_at") or ""))
    if start_at and current < start_at:
        return "upcoming"
    if end_at and current > end_at:
        return "ended"
    if start_at or end_at:
        return "ongoing"
    return "draft"


def season_status_label(entry: dict[str, Any]) -> str:
    return {
        "upcoming": "未开始",
        "ongoing": "进行中",
        "ended": "已结束",
        "draft": "待排期",
    }.get(get_season_status(entry), "待排期")


def normalize_season_catalog_entry(
    entry: dict[str, Any],
    series_catalog: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    catalog = series_catalog or []
    season_name = str(entry.get("season_name") or "").strip()
    if not season_name:
        return None

    series_slug = str(entry.get("series_slug") or "").strip()
    series_name = str(entry.get("series_name") or "").strip()
    series_code = str(entry.get("series_code") or "").strip()
    competition_name = str(entry.get("competition_name") or "").strip()
    if not series_slug:
        if competition_name:
            context = build_series_context_from_competition(competition_name, catalog)
            series_slug = context["series_slug"]
            series_name = series_name or context["series_name"]
            series_code = series_code or context["series_code"]
        elif series_name:
            series_code = series_code or build_competition_code(series_name)
            series_slug = build_series_slug(series_name, series_code)
    if not series_slug:
        return None
    if not series_name:
        matching_entries = get_series_entries_by_slug(catalog, series_slug)
        if matching_entries:
            series_name = matching_entries[0]["series_name"]
            series_code = series_code or matching_entries[0]["series_code"]
    if not series_name:
        series_name = series_slug
    if not series_code:
        series_code = build_competition_code(series_name)
    if not competition_name and series_slug:
        matching_entries = get_series_entries_by_slug(catalog, series_slug)
        if len(matching_entries) == 1:
            competition_name = matching_entries[0]["competition_name"]

    registered_team_ids = [
        str(team_id).strip()
        for team_id in entry.get("registered_team_ids", [])
        if str(team_id).strip()
    ]

    return {
        "series_slug": series_slug,
        "series_name": series_name,
        "series_code": series_code,
        "competition_name": competition_name,
        "season_name": season_name,
        "start_at": normalize_datetime_local_value(str(entry.get("start_at") or "")),
        "end_at": normalize_datetime_local_value(str(entry.get("end_at") or "")),
        "registered_team_ids": merge_team_ids(registered_team_ids),
        "notes": str(entry.get("notes") or "").strip(),
        "created_by": str(entry.get("created_by") or "system").strip() or "system",
        "created_on": str(entry.get("created_on") or china_today_label()).strip()
        or china_today_label(),
    }


def season_sort_key(entry: dict[str, Any]) -> tuple[int, str, str]:
    status_rank = {
        "ongoing": 0,
        "upcoming": 1,
        "draft": 2,
        "ended": 3,
    }.get(get_season_status(entry), 4)
    start_at = str(entry.get("start_at") or "")
    return (status_rank, start_at or "9999-99-99T99:99", entry["season_name"])


def _season_cache_signature(data: dict[str, Any]) -> tuple[str, tuple[tuple[str, tuple[str, ...]], ...], tuple[str, ...]]:
    stored_value = load_meta_value(SEASON_CATALOG_META_KEY) or ""
    competition_signature = tuple(
        sorted(
            (
                competition_name,
                tuple(stats_list_seasons(data, competition_name)),
            )
            for competition_name in list_competitions(data)
        )
    )
    series_signature = tuple(
        sorted(entry["competition_name"] for entry in load_series_catalog(data))
    )
    return stored_value, competition_signature, series_signature


def load_season_catalog(data: dict[str, Any]) -> list[dict[str, Any]]:
    global _SEASON_CACHE_KEY, _SEASON_CACHE_VALUE
    cache_key = _season_cache_signature(data)
    if _SEASON_CACHE_KEY == cache_key and _SEASON_CACHE_VALUE is not None:
        return [dict(entry) for entry in _SEASON_CACHE_VALUE]

    series_catalog = load_series_catalog(data)
    raw_catalog: Any = []
    if cache_key[0]:
        try:
            raw_catalog = json.loads(cache_key[0])
        except json.JSONDecodeError:
            raw_catalog = []

    catalog_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    if isinstance(raw_catalog, list):
        for raw_entry in raw_catalog:
            if not isinstance(raw_entry, dict):
                continue
            entry = normalize_season_catalog_entry(raw_entry, series_catalog)
            if entry:
                key = (
                    entry["series_slug"],
                    str(entry.get("competition_name") or ""),
                    entry["season_name"],
                )
                existing = catalog_by_key.get(key)
                if not existing:
                    catalog_by_key[key] = entry
                    continue
                catalog_by_key[key] = {
                    **existing,
                    "competition_name": existing.get("competition_name") or entry.get("competition_name", ""),
                    "series_name": existing.get("series_name") or entry["series_name"],
                    "series_code": existing.get("series_code") or entry["series_code"],
                    "start_at": existing.get("start_at") or entry["start_at"],
                    "end_at": existing.get("end_at") or entry["end_at"],
                    "registered_team_ids": merge_team_ids(
                        existing.get("registered_team_ids", []),
                        entry.get("registered_team_ids", []),
                    ),
                    "notes": existing.get("notes") or entry.get("notes", ""),
                }

    for competition_name in list_competitions(data):
        context = build_series_context_from_competition(competition_name, series_catalog)
        for season_name in stats_list_seasons(data, competition_name):
            key = (context["series_slug"], competition_name, season_name)
            if key in catalog_by_key:
                continue
            inferred_entry = normalize_season_catalog_entry(
                {
                    "series_slug": context["series_slug"],
                    "series_name": context["series_name"],
                    "series_code": context["series_code"],
                    "competition_name": competition_name,
                    "season_name": season_name,
                    "start_at": "",
                    "end_at": "",
                    "registered_team_ids": [],
                    "created_by": "system",
                    "created_on": china_today_label(),
                },
                series_catalog,
            )
            if inferred_entry:
                catalog_by_key[key] = inferred_entry

    sorted_catalog = sorted(catalog_by_key.values(), key=season_sort_key)
    _SEASON_CACHE_KEY = cache_key
    _SEASON_CACHE_VALUE = [dict(entry) for entry in sorted_catalog]
    return [dict(entry) for entry in sorted_catalog]


def save_season_catalog(catalog: list[dict[str, Any]]) -> None:
    global _SEASON_CACHE_KEY, _SEASON_CACHE_VALUE
    normalized_catalog = [
        entry
        for entry in (
            normalize_season_catalog_entry(item) if isinstance(item, dict) else None
            for item in catalog
        )
        if entry
    ]
    save_meta_value(
        SEASON_CATALOG_META_KEY,
        json.dumps(normalized_catalog, ensure_ascii=False, indent=2),
    )
    _SEASON_CACHE_KEY = None
    _SEASON_CACHE_VALUE = None


def get_season_entries_for_series(
    catalog: list[dict[str, Any]],
    series_slug: str,
    include_non_ongoing: bool = True,
    competition_name: str | None = None,
) -> list[dict[str, Any]]:
    entries = [
        entry
        for entry in catalog
        if entry["series_slug"] == series_slug
        and (not competition_name or entry.get("competition_name") == competition_name)
        and (include_non_ongoing or get_season_status(entry) == "ongoing")
    ]
    return sorted(entries, key=season_sort_key)


def get_season_entry(
    catalog: list[dict[str, Any]],
    series_slug: str,
    season_name: str,
    competition_name: str | None = None,
) -> dict[str, Any] | None:
    for entry in catalog:
        if (
            entry["series_slug"] == series_slug
            and entry["season_name"] == season_name
            and (not competition_name or entry.get("competition_name") == competition_name)
        ):
            return entry
    return None


def list_seasons(
    data: dict[str, Any],
    competition_name: str | None = None,
    series_slug: str | None = None,
    include_non_ongoing: bool = False,
    selected_season: str | None = None,
) -> list[str]:
    season_catalog = load_season_catalog(data)
    season_names: list[str] = []
    seen: set[str] = set()
    resolved_series_slug = series_slug
    if not resolved_series_slug and competition_name:
        resolved_series_slug = build_series_context_from_competition(
            competition_name,
            load_series_catalog(data),
        )["series_slug"]

    if resolved_series_slug:
        for entry in get_season_entries_for_series(
            season_catalog,
            resolved_series_slug,
            include_non_ongoing=include_non_ongoing,
            competition_name=competition_name,
        ):
            if entry["season_name"] in seen:
                continue
            seen.add(entry["season_name"])
            season_names.append(entry["season_name"])

    for season_name in stats_list_seasons(data, competition_name):
        if season_name in seen:
            continue
        if not include_non_ongoing and selected_season != season_name:
            continue
        seen.add(season_name)
        season_names.append(season_name)
    if selected_season and selected_season not in seen:
        season_names.append(selected_season)
    return season_names
