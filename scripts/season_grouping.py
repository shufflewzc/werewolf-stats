from __future__ import annotations

import hashlib
import json
from typing import Any

from competition_meta import resolve_season_policy_for_scope
from generate_stats import (
    build_team_rows,
    get_match_competition_name,
    is_team_score_excluded,
    normalize_stance_result,
    safe_rate,
)
from season_policy import (
    LEGACY_TARGET_COMPETITION_NAME,
    LEGACY_TARGET_SEASON_NAME,
    get_grouping_source,
    get_leaderboard_sections,
    get_stage_policy,
    group_badge_style,
    group_for_rank,
    legacy_policy_for_scope,
    legacy_target_season_policy,
    progression_badge,
    section_for_group,
    stage_display,
)


TARGET_COMPETITION_NAME = LEGACY_TARGET_COMPETITION_NAME
TARGET_SEASON_NAME = LEGACY_TARGET_SEASON_NAME
REGULAR_SEASON_STAGE = "regular_season"
PLACEMENT_STAGE = "placement"
GROUP_LABELS = ("S1", "S2", "S3", "S4", "F1", "F2", "F3", "F4")
EXPECTED_TEAM_COUNT = 32


def is_target_scope(competition_name: object, season_name: object) -> bool:
    """Compatibility helper for the original S2 rollout scripts and tests."""
    return (
        str(competition_name or "").strip() == TARGET_COMPETITION_NAME
        and str(season_name or "").strip() == TARGET_SEASON_NAME
    )


def resolve_policy(
    data: dict[str, Any],
    competition_name: object,
    season_name: object,
) -> dict[str, Any]:
    normalized_competition = str(competition_name or "").strip()
    normalized_season = str(season_name or "").strip()
    try:
        return resolve_season_policy_for_scope(
            data,
            normalized_competition,
            normalized_season,
        )
    except (KeyError, TypeError):
        legacy_policy = legacy_policy_for_scope(
            normalized_competition,
            normalized_season,
        )
        if legacy_policy:
            return legacy_policy
        raise


def is_grouping_scope(
    data: dict[str, Any],
    competition_name: object,
    season_name: object,
) -> bool:
    policy = resolve_policy(data, competition_name, season_name)
    return bool(get_grouping_source(policy) or any(
        get_leaderboard_sections(policy, stage)
        for stage in policy.get("stages", {})
    ))


def placement_group_for_rank(
    rank: int,
    policy: dict[str, Any] | None = None,
) -> str:
    return group_for_rank(policy or legacy_target_season_policy(), rank)


def group_tier(group_label: object) -> str:
    """Compatibility helper; generic code uses policy section membership."""
    normalized = str(group_label or "").strip().upper()
    return normalized[0] if normalized else ""


def group_sort_key(
    group_label: object,
    policy: dict[str, Any] | None = None,
) -> tuple[int, str]:
    normalized = str(group_label or "").strip().upper()
    source = get_grouping_source(policy or legacy_target_season_policy())
    labels = [
        str(row.get("group") or "").strip().upper()
        for row in ((source or ("", {}))[1].get("ranges", []))
    ]
    try:
        return (labels.index(normalized), normalized)
    except ValueError:
        return (len(labels), normalized)


def progress_status(
    tier: object,
    rank: int,
    policy: dict[str, Any] | None = None,
    stage: str = REGULAR_SEASON_STAGE,
) -> str:
    badge = progression_badge(
        policy or legacy_target_season_policy(),
        stage,
        tier,
        rank,
    )
    return str(badge.get("text") or "") if badge else ""


def get_team_stage_group(
    team: dict[str, Any] | None,
    stage: str,
) -> str:
    if not team:
        return ""
    for item in team.get("stage_groups", []) or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("stage") or "").strip() != stage:
            continue
        return str(item.get("group_label") or "").strip().upper()
    return ""


def get_team_regular_season_group(team: dict[str, Any] | None) -> str:
    return get_team_stage_group(team, REGULAR_SEASON_STAGE)


def build_team_group_map(
    data: dict[str, Any],
    competition_name: str | None = None,
    season_name: str | None = None,
    group_stage: str = REGULAR_SEASON_STAGE,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for team in data.get("teams", []):
        if (
            competition_name
            and str(team.get("competition_name") or "").strip() != competition_name
        ):
            continue
        if (
            season_name
            and str(team.get("season_name") or "").strip() != season_name
        ):
            continue
        group_label = get_team_stage_group(team, group_stage)
        team_id = str(team.get("team_id") or "").strip()
        if team_id and group_label:
            result[team_id] = group_label
    return result


def build_placement_assignment_preview(
    data: dict[str, Any],
    competition_name: str = TARGET_COMPETITION_NAME,
    season_name: str = TARGET_SEASON_NAME,
) -> dict[str, Any]:
    policy = resolve_policy(data, competition_name, season_name)
    grouping_source = get_grouping_source(policy)
    if not grouping_source:
        return {
            "competition_name": competition_name,
            "season_name": season_name,
            "source_stage": "",
            "assignment_stage": "",
            "expected_team_count": 0,
            "team_count": 0,
            "ready": False,
            "revision": "",
            "rows": [],
            "error": "当前赛季策略没有启用按排名分组。",
        }
    source_stage, grouping = grouping_source
    assignment_stage = str(
        grouping.get("assignment_stage") or REGULAR_SEASON_STAGE
    )
    expected_team_count = max(
        (int(row.get("to") or 0) for row in grouping.get("ranges", [])),
        default=0,
    )
    placement_matches = [
        match
        for match in data.get("matches", [])
        if str(get_match_competition_name(match) or "").strip() == competition_name
        and str(match.get("season") or "").strip() == season_name
        and str(match.get("stage") or "").strip() == source_stage
        and bool(match.get("players"))
    ]
    scoped_data = {**data, "matches": placement_matches}
    ranked_rows = [
        row
        for row in build_team_rows(scoped_data, competition_name, season_name)
        if int(row.get("matches_represented") or 0) > 0
    ]
    team_lookup = {
        str(team.get("team_id") or ""): team
        for team in data.get("teams", [])
        if str(team.get("competition_name") or "").strip() == competition_name
        and str(team.get("season_name") or "").strip() == season_name
    }
    rows: list[dict[str, Any]] = []
    for index, ranked_row in enumerate(ranked_rows, start=1):
        team_id = str(ranked_row.get("team_id") or "")
        rows.append(
            {
                "rank": index,
                "team_id": team_id,
                "team_name": str(ranked_row.get("name") or team_id),
                "points_total": round(
                    float(ranked_row.get("points_earned_total") or 0.0),
                    2,
                ),
                "matches_represented": int(
                    ranked_row.get("matches_represented") or 0
                ),
                "win_rate": round(float(ranked_row.get("win_rate") or 0.0), 8),
                "stance_rate": round(
                    float(ranked_row.get("stance_rate") or 0.0),
                    8,
                ),
                "current_group": get_team_stage_group(
                    team_lookup.get(team_id),
                    assignment_stage,
                ),
                "proposed_group": group_for_rank(policy, index),
            }
        )
    revision_source = {
        "competition_name": competition_name,
        "season_name": season_name,
        "policy_version": int(policy.get("version") or 1),
        "source_stage": source_stage,
        "assignment_stage": assignment_stage,
        "rows": [
            {
                key: row[key]
                for key in (
                    "rank",
                    "team_id",
                    "points_total",
                    "matches_represented",
                    "win_rate",
                    "stance_rate",
                    "proposed_group",
                )
            }
            for row in rows
        ],
    }
    revision = hashlib.sha256(
        json.dumps(
            revision_source,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "competition_name": competition_name,
        "season_name": season_name,
        "source_stage": source_stage,
        "assignment_stage": assignment_stage,
        "expected_team_count": expected_team_count,
        "team_count": len(rows),
        "ready": bool(expected_team_count and len(rows) == expected_team_count),
        "revision": revision,
        "rows": rows,
        "error": "",
    }


def apply_placement_assignments(
    data: dict[str, Any],
    expected_revision: str,
    competition_name: str = TARGET_COMPETITION_NAME,
    season_name: str = TARGET_SEASON_NAME,
) -> tuple[int, str]:
    preview = build_placement_assignment_preview(
        data,
        competition_name,
        season_name,
    )
    if preview.get("error"):
        raise ValueError(str(preview["error"]))
    if not preview["ready"]:
        raise ValueError(
            "分组来源榜必须恰好有 "
            f"{preview['expected_team_count']} 支有效战队，当前为 "
            f"{preview['team_count']} 支。"
        )
    if not expected_revision or expected_revision != preview["revision"]:
        raise ValueError("分组来源排行榜已变化，请刷新预览后重新确认分组。")
    assignment_by_team_id = {
        str(row["team_id"]): str(row["proposed_group"])
        for row in preview["rows"]
    }
    assignment_stage = str(preview["assignment_stage"])
    updated_count = 0
    for team in data.get("teams", []):
        if str(team.get("competition_name") or "").strip() != competition_name:
            continue
        if str(team.get("season_name") or "").strip() != season_name:
            continue
        team_id = str(team.get("team_id") or "")
        proposed_group = assignment_by_team_id.get(team_id)
        if not proposed_group:
            continue
        preserved_groups = [
            item
            for item in team.get("stage_groups", []) or []
            if isinstance(item, dict)
            and str(item.get("stage") or "").strip() != assignment_stage
        ]
        team["stage_groups"] = [
            *preserved_groups,
            {"stage": assignment_stage, "group_label": proposed_group},
        ]
        updated_count += 1
    return updated_count, str(preview["revision"])


def build_regular_season_team_leaderboards(
    data: dict[str, Any],
    competition_name: str = TARGET_COMPETITION_NAME,
    season_name: str = TARGET_SEASON_NAME,
    stage: str = REGULAR_SEASON_STAGE,
) -> dict[str, list[dict[str, Any]]]:
    policy = resolve_policy(data, competition_name, season_name)
    sections = get_leaderboard_sections(policy, stage)
    if not sections:
        return {}
    stage_config = get_stage_policy(policy, stage)
    ranking_mode = str(
        (stage_config.get("standings") or {}).get("ranking") or "points"
    )
    display = stage_display(policy, stage)
    grouping_source = get_grouping_source(policy)
    default_group_stage = (
        str(grouping_source[1].get("assignment_stage") or stage)
        if grouping_source
        else stage
    )
    group_stage = str(display.get("group_stage") or default_group_stage)
    team_lookup = {
        str(team.get("team_id") or ""): team
        for team in data.get("teams", [])
        if str(team.get("competition_name") or "").strip() == competition_name
        and str(team.get("season_name") or "").strip() == season_name
    }
    team_group_map = build_team_group_map(
        data,
        competition_name,
        season_name,
        group_stage,
    )
    boards: dict[str, dict[str, dict[str, Any]]] = {
        str(section["key"]): {} for section in sections
    }
    represented_players: dict[str, set[str]] = {}
    for team_id, group_label in team_group_map.items():
        section_key = section_for_group(policy, stage, group_label)
        team = team_lookup.get(team_id)
        if section_key not in boards or not team:
            continue
        boards[section_key][team_id] = {
            "team_id": team_id,
            "name": str(team.get("name") or team_id),
            "short_name": str(
                team.get("short_name") or team.get("name") or team_id
            ),
            "logo": str(team.get("logo") or ""),
            "matches_represented": 0,
            "player_appearances": 0,
            "player_count": 0,
            "wins": 0,
            "losses": 0,
            "stance_calls": 0,
            "correct_stance_calls": 0,
            "points_earned_total": 0.0,
            "group_label": group_label,
            "regular_season_group": group_label,
            "badges": [],
        }
        represented_players[team_id] = set()

    for match in data.get("matches", []):
        if str(get_match_competition_name(match) or "").strip() != competition_name:
            continue
        if str(match.get("season") or "").strip() != season_name:
            continue
        if str(match.get("stage") or "").strip() != stage:
            continue
        if not match.get("players") or is_team_score_excluded(match):
            continue
        represented_team_ids: set[str] = set()
        for participant in match.get("players", []):
            team_id = str(participant.get("team_id") or "")
            section_key = section_for_group(
                policy,
                stage,
                team_group_map.get(team_id),
            )
            row = boards.get(section_key, {}).get(team_id)
            if not row:
                continue
            represented_team_ids.add(team_id)
            row["player_appearances"] += 1
            row["wins"] += 1 if participant.get("result") == "win" else 0
            row["losses"] += 1 if participant.get("result") == "loss" else 0
            row["points_earned_total"] += float(
                participant.get("points_earned") or 0.0
            )
            player_id = str(participant.get("player_id") or "")
            if player_id:
                represented_players[team_id].add(player_id)
            stance_result = normalize_stance_result(participant)
            if stance_result != "none":
                row["stance_calls"] += 1
                if stance_result == "correct":
                    row["correct_stance_calls"] += 1
        for team_id in represented_team_ids:
            section_key = section_for_group(
                policy,
                stage,
                team_group_map.get(team_id),
            )
            boards[section_key][team_id]["matches_represented"] += 1

    result: dict[str, list[dict[str, Any]]] = {}
    for section in sections:
        section_key = str(section["key"])
        rows: list[dict[str, Any]] = []
        for team_id, row in boards[section_key].items():
            appearances = int(row["player_appearances"])
            row["player_count"] = len(represented_players.get(team_id, set()))
            row["points_earned_total"] = round(
                float(row["points_earned_total"]),
                2,
            )
            row["win_rate"] = (
                safe_rate(int(row["wins"]), appearances) if appearances else 0.0
            )
            row["stance_rate"] = (
                safe_rate(
                    int(row["correct_stance_calls"]),
                    int(row["stance_calls"]),
                )
                if row["stance_calls"]
                else 0.0
            )
            row["points_per_match"] = (
                round(
                    row["points_earned_total"] / row["matches_represented"],
                    2,
                )
                if row["matches_represented"]
                else 0.0
            )
            rows.append(row)
        if ranking_mode == "average_points":
            rows.sort(
                key=lambda item: (
                    -float(item["points_per_match"]),
                    -float(item["points_earned_total"]),
                    -float(item["win_rate"]),
                    str(item["name"]),
                )
            )
        elif ranking_mode == "win_rate":
            rows.sort(
                key=lambda item: (
                    -float(item["win_rate"]),
                    -float(item["points_earned_total"]),
                    -int(item["matches_represented"]),
                    str(item["name"]),
                )
            )
        else:
            rows.sort(
                key=lambda item: (
                    -float(item["points_earned_total"]),
                    -int(item["matches_represented"]),
                    -float(item["win_rate"]),
                    str(item["name"]),
                )
            )
        for index, row in enumerate(rows, start=1):
            row["rank"] = index
            row["points_rank"] = index
            badges: list[dict[str, str]] = []
            if display.get("show_team_group") and row.get("group_label"):
                badges.append(
                    {
                        "text": str(row["group_label"]),
                        "style": group_badge_style(policy, row["group_label"]),
                        "kind": "group",
                    }
                )
            progress = progression_badge(
                policy,
                stage,
                section_key,
                index,
            )
            if progress:
                badges.append(progress)
                row["progress_status"] = progress["text"]
            row["badges"] = badges
            if not display.get("show_team_group"):
                # Do not leak subgroup labels through legacy leaderboard fields.
                # Older mini-program releases build their own group badge from
                # these fields even when the canonical badges list omits it.
                row.pop("group_label", None)
                row.pop("regular_season_group", None)
        result[section_key] = rows
    return result


def build_team_leaderboard_sections(
    data: dict[str, Any],
    competition_name: str,
    season_name: str,
    stage: str,
) -> list[dict[str, Any]]:
    policy = resolve_policy(data, competition_name, season_name)
    boards = build_regular_season_team_leaderboards(
        data,
        competition_name,
        season_name,
        stage,
    )
    return [
        {
            "key": str(section["key"]),
            "label": str(section["label"]),
            "title": str(section.get("title") or f"{section['label']}榜"),
            "rows": boards.get(str(section["key"]), []),
        }
        for section in get_leaderboard_sections(policy, stage)
    ]


def team_group_badge_for_stage(
    data: dict[str, Any],
    competition_name: str,
    season_name: str,
    team_id: str,
    stage: str,
) -> dict[str, str] | None:
    policy = resolve_policy(data, competition_name, season_name)
    display = stage_display(policy, stage)
    if not display.get("show_team_group"):
        return None
    grouping_source = get_grouping_source(policy)
    default_group_stage = (
        str(grouping_source[1].get("assignment_stage") or stage)
        if grouping_source
        else stage
    )
    group_stage = str(display.get("group_stage") or default_group_stage)
    group_label = build_team_group_map(
        data,
        competition_name,
        season_name,
        group_stage,
    ).get(team_id, "")
    if not group_label:
        return None
    return {
        "text": group_label,
        "style": group_badge_style(policy, group_label),
        "kind": "group",
    }


def match_group_labels(
    data: dict[str, Any],
    match: dict[str, Any],
) -> list[str]:
    competition_name = str(get_match_competition_name(match) or "").strip()
    season_name = str(match.get("season") or "").strip()
    stage = str(match.get("stage") or "").strip()
    policy = resolve_policy(data, competition_name, season_name)
    display = stage_display(policy, stage)
    if not display.get("show_match_groups"):
        return []
    grouping_source = get_grouping_source(policy)
    default_group_stage = (
        str(grouping_source[1].get("assignment_stage") or stage)
        if grouping_source
        else stage
    )
    group_stage = str(display.get("group_stage") or default_group_stage)
    team_group_map = build_team_group_map(
        data,
        competition_name,
        season_name,
        group_stage,
    )
    labels = {
        team_group_map.get(str(participant.get("team_id") or ""), "")
        for participant in match.get("players", [])
    }
    return sorted(
        (label for label in labels if label),
        key=lambda label: group_sort_key(label, policy),
    )


def match_team_group_map(
    data: dict[str, Any],
    match: dict[str, Any],
) -> dict[str, str]:
    competition_name = str(get_match_competition_name(match) or "").strip()
    season_name = str(match.get("season") or "").strip()
    stage = str(match.get("stage") or "").strip()
    policy = resolve_policy(data, competition_name, season_name)
    display = stage_display(policy, stage)
    if not display.get("show_match_groups"):
        return {}
    grouping_source = get_grouping_source(policy)
    default_group_stage = (
        str(grouping_source[1].get("assignment_stage") or stage)
        if grouping_source
        else stage
    )
    return build_team_group_map(
        data,
        competition_name,
        season_name,
        str(display.get("group_stage") or default_group_stage),
    )


def progression_is_display_only(
    data: dict[str, Any],
    competition_name: object,
    season_name: object,
) -> bool:
    policy = resolve_policy(data, competition_name, season_name)
    return any(
        bool(get_stage_policy(policy, stage).get("progression"))
        for stage in policy.get("stages", {})
    )
