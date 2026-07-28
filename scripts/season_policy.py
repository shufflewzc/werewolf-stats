from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


POLICY_SCHEMA_VERSION = 1
POLICY_PRESET_STANDARD = "standard_league"
POLICY_PRESET_TIERED = "tiered_league"
POLICY_PRESET_KNOCKOUT = "knockout"
POLICY_PRESETS = {
    POLICY_PRESET_STANDARD: "普通积分赛",
    POLICY_PRESET_TIERED: "分层积分赛",
    POLICY_PRESET_KNOCKOUT: "淘汰赛",
}
POLICY_STATUSES = {"published"}
LEADERBOARD_MODES = {"unified", "tiered"}
RANKING_MODES = {"points", "average_points", "win_rate"}
GROUPING_METHODS = {"none", "rank_ranges"}
BADGE_STYLES = {"gold", "blue", "green", "red", "gray", "orange"}
MAX_GROUP_RANGES = 64
MAX_BOARD_SECTIONS = 12
MAX_PROGRESS_BANDS = 64
CHINA_TZ = ZoneInfo("Asia/Shanghai")

LEGACY_TARGET_COMPETITION_NAME = "京城大师赛广州公开赛"
LEGACY_TARGET_SEASON_NAME = "2026广州公开赛S2"


def _clean_text(value: object, default: str = "") -> str:
    return str(value or "").strip() or default


def _positive_int(value: object, default: int = 0) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return default


def _badge_style(value: object, default: str = "gray") -> str:
    normalized = _clean_text(value).lower()
    return normalized if normalized in BADGE_STYLES else default


def default_season_policy(
    preset: str = POLICY_PRESET_STANDARD,
    *,
    inherit: bool = False,
) -> dict[str, Any]:
    if inherit:
        return {"inherit": True}
    normalized_preset = preset if preset in POLICY_PRESETS else POLICY_PRESET_STANDARD
    return {
        "inherit": False,
        "schema_version": POLICY_SCHEMA_VERSION,
        "preset": normalized_preset,
        "version": 1,
        "status": "published",
        "updated_at": "",
        "stages": {},
    }


def build_tiered_league_policy(
    *,
    group_labels: list[str],
    group_size: int,
    sections: list[dict[str, Any]],
    progression: dict[str, list[dict[str, Any]]],
    source_stage: str = "placement",
    target_stage: str = "regular_season",
    ranking_mode: str = "points",
) -> dict[str, Any]:
    clean_labels = [_clean_text(label).upper() for label in group_labels if _clean_text(label)]
    size = max(1, int(group_size or 1))
    ranges = [
        {
            "from": index * size + 1,
            "to": (index + 1) * size,
            "group": label,
            "style": "gold" if index < max(1, len(clean_labels) // 2) else "blue",
        }
        for index, label in enumerate(clean_labels)
    ]
    raw_policy = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "preset": POLICY_PRESET_TIERED,
        "version": 1,
        "status": "published",
        "stages": {
            source_stage: {
                "grouping": {
                    "method": "rank_ranges",
                    "assignment_stage": target_stage,
                    "freeze_after_confirm": True,
                    "ranges": ranges,
                },
                "display": {
                    "show_team_group": True,
                    "show_personal_group": False,
                    "show_match_groups": False,
                },
            },
            target_stage: {
                "standings": {
                    "mode": "tiered",
                    "ranking": (
                        ranking_mode
                        if ranking_mode in RANKING_MODES
                        else "points"
                    ),
                    "sections": sections,
                },
                "progression": progression,
                "display": {
                    "show_team_group": True,
                    "show_personal_group": False,
                    "show_match_groups": True,
                    "group_stage": target_stage,
                },
            },
        },
    }
    return normalize_season_policy(raw_policy)


def legacy_target_season_policy() -> dict[str, Any]:
    return build_tiered_league_policy(
        group_labels=["S1", "S2", "S3", "S4", "F1", "F2", "F3", "F4"],
        group_size=4,
        sections=[
            {
                "key": "S",
                "label": "S组",
                "title": "S组常规赛榜",
                "groups": ["S1", "S2", "S3", "S4"],
            },
            {
                "key": "F",
                "label": "F组",
                "title": "F组常规赛榜",
                "groups": ["F1", "F2", "F3", "F4"],
            },
        ],
        progression={
            "S": [
                {"from": 1, "to": 2, "status": "直通", "style": "orange"},
                {"from": 3, "to": 11, "status": "晋级", "style": "green"},
                {"from": 12, "to": 16, "status": "淘汰", "style": "red"},
            ],
            "F": [
                {"from": 1, "to": 1, "status": "直通", "style": "orange"},
                {"from": 2, "to": 8, "status": "晋级", "style": "green"},
                {"from": 9, "to": 16, "status": "淘汰", "style": "red"},
            ],
        },
    )


def legacy_policy_for_scope(
    competition_name: object,
    season_name: object,
) -> dict[str, Any] | None:
    if (
        _clean_text(competition_name) == LEGACY_TARGET_COMPETITION_NAME
        and _clean_text(season_name) == LEGACY_TARGET_SEASON_NAME
    ):
        return legacy_target_season_policy()
    return None


def _normalize_group_ranges(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for raw in value[:MAX_GROUP_RANGES]:
        if not isinstance(raw, dict):
            continue
        start = _positive_int(raw.get("from"))
        end = _positive_int(raw.get("to"))
        group = _clean_text(raw.get("group")).upper()
        if not start or not end or not group:
            continue
        rows.append(
            {
                "from": start,
                "to": end,
                "group": group,
                "style": _badge_style(raw.get("style")),
            }
        )
    return rows


def _normalize_sections(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sections: list[dict[str, Any]] = []
    for raw in value[:MAX_BOARD_SECTIONS]:
        if not isinstance(raw, dict):
            continue
        key = _clean_text(raw.get("key")).upper()
        label = _clean_text(raw.get("label"), key)
        groups = [
            _clean_text(group).upper()
            for group in (raw.get("groups") if isinstance(raw.get("groups"), list) else [])
            if _clean_text(group)
        ]
        if not key or not groups:
            continue
        sections.append(
            {
                "key": key,
                "label": label,
                "title": _clean_text(raw.get("title"), f"{label}榜"),
                "groups": list(dict.fromkeys(groups)),
            }
        )
    return sections


def _normalize_progression(value: object) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    for raw_key, raw_bands in list(value.items())[:MAX_BOARD_SECTIONS]:
        key = _clean_text(raw_key).upper()
        if not key or not isinstance(raw_bands, list):
            continue
        bands: list[dict[str, Any]] = []
        for raw in raw_bands[:MAX_PROGRESS_BANDS]:
            if not isinstance(raw, dict):
                continue
            start = _positive_int(raw.get("from"))
            end = _positive_int(raw.get("to"))
            status = _clean_text(raw.get("status"))
            if not start or not end or not status:
                continue
            bands.append(
                {
                    "from": start,
                    "to": end,
                    "status": status,
                    "style": _badge_style(raw.get("style"), "green"),
                }
            )
        if bands:
            result[key] = bands
    return result


def _normalize_stage_policy(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    raw_grouping = value.get("grouping")
    if isinstance(raw_grouping, dict):
        method = _clean_text(raw_grouping.get("method"), "none")
        if method not in GROUPING_METHODS:
            method = "none"
        result["grouping"] = {
            "method": method,
            "assignment_stage": _clean_text(
                raw_grouping.get("assignment_stage"),
                "regular_season",
            ),
            "freeze_after_confirm": bool(
                raw_grouping.get("freeze_after_confirm", True)
            ),
            "ranges": _normalize_group_ranges(raw_grouping.get("ranges")),
        }
    raw_standings = value.get("standings")
    if isinstance(raw_standings, dict):
        mode = _clean_text(raw_standings.get("mode"), "unified")
        if mode not in LEADERBOARD_MODES:
            mode = "unified"
        result["standings"] = {
            "mode": mode,
            "ranking": (
                _clean_text(raw_standings.get("ranking"), "points")
                if _clean_text(raw_standings.get("ranking"), "points")
                in RANKING_MODES
                else "points"
            ),
            "sections": _normalize_sections(raw_standings.get("sections")),
        }
    progression = _normalize_progression(value.get("progression"))
    if progression:
        result["progression"] = progression
    raw_display = value.get("display")
    if isinstance(raw_display, dict):
        result["display"] = {
            "show_team_group": bool(raw_display.get("show_team_group")),
            "show_personal_group": bool(raw_display.get("show_personal_group")),
            "show_match_groups": bool(raw_display.get("show_match_groups")),
            "group_stage": _clean_text(
                raw_display.get("group_stage"),
                "regular_season",
            ),
        }
    return result


def normalize_season_policy(
    value: object,
    *,
    allow_inherit: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"inherit": True} if allow_inherit else default_season_policy()
    if allow_inherit and bool(value.get("inherit")):
        return {"inherit": True}
    preset = _clean_text(value.get("preset"), POLICY_PRESET_STANDARD)
    if preset not in POLICY_PRESETS:
        preset = POLICY_PRESET_STANDARD
    raw_stages = value.get("stages")
    stages: dict[str, dict[str, Any]] = {}
    if isinstance(raw_stages, dict):
        for raw_stage, raw_policy in raw_stages.items():
            stage = _clean_text(raw_stage)
            if not stage:
                continue
            normalized_stage = _normalize_stage_policy(raw_policy)
            if normalized_stage:
                stages[stage] = normalized_stage
    try:
        version = max(1, int(value.get("version") or 1))
    except (TypeError, ValueError):
        version = 1
    status = _clean_text(value.get("status"), "published")
    if status not in POLICY_STATUSES:
        status = "published"
    return {
        "inherit": False,
        "schema_version": POLICY_SCHEMA_VERSION,
        "preset": preset,
        "version": version,
        "status": status,
        "updated_at": _clean_text(value.get("updated_at")),
        "stages": stages,
    }


def merge_season_policies(
    series_policy: dict[str, Any] | None,
    season_policy: dict[str, Any] | None,
) -> dict[str, Any]:
    base = normalize_season_policy(series_policy)
    override = normalize_season_policy(season_policy, allow_inherit=True)
    return base if override.get("inherit") else override


def version_season_policy(
    value: dict[str, Any] | None,
    previous: dict[str, Any] | None = None,
    *,
    allow_inherit: bool = False,
) -> dict[str, Any]:
    normalized = normalize_season_policy(value, allow_inherit=allow_inherit)
    if normalized.get("inherit"):
        return {"inherit": True}
    previous_normalized = normalize_season_policy(
        previous,
        allow_inherit=allow_inherit,
    )
    has_previous = isinstance(previous, dict) and bool(previous)
    comparable_keys = ("preset", "stages")
    unchanged = (
        has_previous
        and not previous_normalized.get("inherit")
        and all(
            normalized.get(key) == previous_normalized.get(key)
            for key in comparable_keys
        )
    )
    if unchanged:
        normalized["version"] = int(previous_normalized.get("version") or 1)
        normalized["updated_at"] = _clean_text(previous_normalized.get("updated_at"))
        return normalized
    previous_version = (
        int(previous_normalized.get("version") or 0)
        if has_previous and not previous_normalized.get("inherit")
        else 0
    )
    normalized["version"] = max(1, previous_version + 1)
    normalized["updated_at"] = (
        datetime.now(CHINA_TZ).replace(microsecond=0).isoformat()
    )
    return normalized


def validate_season_policy(policy: dict[str, Any] | None) -> list[str]:
    normalized = normalize_season_policy(policy, allow_inherit=True)
    if normalized.get("inherit"):
        return []
    errors: list[str] = []
    for stage, config in normalized.get("stages", {}).items():
        grouping = config.get("grouping") or {}
        if grouping.get("method") == "rank_ranges":
            ranges = grouping.get("ranges") or []
            if not ranges:
                errors.append(f"{stage}：按排名分组至少需要一个区间")
            occupied: set[int] = set()
            groups: set[str] = set()
            for row in ranges:
                start = int(row["from"])
                end = int(row["to"])
                group = str(row["group"])
                if start > end:
                    errors.append(f"{stage}：分组 {group} 的开始名次不能大于结束名次")
                    continue
                if group in groups:
                    errors.append(f"{stage}：分组名称 {group} 重复")
                groups.add(group)
                for rank in range(start, end + 1):
                    if rank in occupied:
                        errors.append(f"{stage}：第 {rank} 名被多个分组区间覆盖")
                        break
                    occupied.add(rank)
            if occupied and occupied != set(range(1, max(occupied) + 1)):
                errors.append(f"{stage}：分组名次必须从第1名开始连续覆盖")
        standings = config.get("standings") or {}
        if standings.get("mode") == "tiered":
            sections = standings.get("sections") or []
            if not sections:
                errors.append(f"{stage}：分层榜单至少需要一个榜单分区")
            section_keys: set[str] = set()
            section_groups: set[str] = set()
            for section in sections:
                key = str(section["key"])
                if key in section_keys:
                    errors.append(f"{stage}：榜单分区标识 {key} 重复")
                section_keys.add(key)
                for group in section.get("groups", []):
                    if group in section_groups:
                        errors.append(f"{stage}：分组 {group} 被多个榜单分区引用")
                    section_groups.add(group)
            for key, bands in (config.get("progression") or {}).items():
                if key not in section_keys:
                    errors.append(f"{stage}：晋级规则引用了不存在的分区 {key}")
                occupied_ranks: set[int] = set()
                for band in bands:
                    start = int(band["from"])
                    end = int(band["to"])
                    if start > end:
                        errors.append(f"{stage}/{key}：晋级区间开始名次不能大于结束名次")
                        continue
                    for rank in range(start, end + 1):
                        if rank in occupied_ranks:
                            errors.append(f"{stage}/{key}：第 {rank} 名存在重复状态")
                            break
                        occupied_ranks.add(rank)
    return list(dict.fromkeys(errors))


def get_stage_policy(
    policy: dict[str, Any] | None,
    stage: object,
) -> dict[str, Any]:
    normalized = normalize_season_policy(policy)
    return dict(normalized.get("stages", {}).get(_clean_text(stage), {}))


def get_grouping_source(
    policy: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]] | None:
    normalized = normalize_season_policy(policy)
    for stage, config in normalized.get("stages", {}).items():
        grouping = config.get("grouping") or {}
        if grouping.get("method") == "rank_ranges" and grouping.get("ranges"):
            return stage, dict(grouping)
    return None


def group_for_rank(
    policy: dict[str, Any] | None,
    rank: int,
) -> str:
    source = get_grouping_source(policy)
    if not source:
        return ""
    for row in source[1].get("ranges", []):
        if int(row["from"]) <= int(rank) <= int(row["to"]):
            return str(row["group"])
    return ""


def group_badge_style(
    policy: dict[str, Any] | None,
    group_label: object,
) -> str:
    normalized_group = _clean_text(group_label).upper()
    source = get_grouping_source(policy)
    if not source:
        return "gray"
    for row in source[1].get("ranges", []):
        if str(row["group"]).upper() == normalized_group:
            return _badge_style(row.get("style"))
    return "gray"


def get_leaderboard_sections(
    policy: dict[str, Any] | None,
    stage: object,
) -> list[dict[str, Any]]:
    config = get_stage_policy(policy, stage)
    standings = config.get("standings") or {}
    if standings.get("mode") != "tiered":
        return []
    return [dict(section) for section in standings.get("sections", [])]


def section_for_group(
    policy: dict[str, Any] | None,
    stage: object,
    group_label: object,
) -> str:
    normalized_group = _clean_text(group_label).upper()
    for section in get_leaderboard_sections(policy, stage):
        if normalized_group in section.get("groups", []):
            return str(section["key"])
    return ""


def progression_badge(
    policy: dict[str, Any] | None,
    stage: object,
    section_key: object,
    rank: int,
) -> dict[str, str] | None:
    config = get_stage_policy(policy, stage)
    bands = (config.get("progression") or {}).get(
        _clean_text(section_key).upper(),
        [],
    )
    for band in bands:
        if int(band["from"]) <= int(rank) <= int(band["to"]):
            return {
                "text": str(band["status"]),
                "style": _badge_style(band.get("style"), "green"),
                "kind": "progress",
            }
    return None


def stage_display(
    policy: dict[str, Any] | None,
    stage: object,
) -> dict[str, Any]:
    config = get_stage_policy(policy, stage)
    return dict(config.get("display") or {})
