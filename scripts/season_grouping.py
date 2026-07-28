from __future__ import annotations

import hashlib
import json
from typing import Any

from generate_stats import (
    build_team_rows,
    get_match_competition_name,
    is_team_score_excluded,
    normalize_stance_result,
    safe_rate,
)


TARGET_COMPETITION_NAME = "京城大师赛广州公开赛"
TARGET_SEASON_NAME = "2026广州公开赛S2"
REGULAR_SEASON_STAGE = "regular_season"
PLACEMENT_STAGE = "placement"
GROUP_LABELS = ("S1", "S2", "S3", "S4", "F1", "F2", "F3", "F4")
EXPECTED_TEAM_COUNT = 32


def is_target_scope(competition_name: object, season_name: object) -> bool:
    return (
        str(competition_name or "").strip() == TARGET_COMPETITION_NAME
        and str(season_name or "").strip() == TARGET_SEASON_NAME
    )


def placement_group_for_rank(rank: int) -> str:
    if rank < 1 or rank > EXPECTED_TEAM_COUNT:
        return ""
    return GROUP_LABELS[(rank - 1) // 4]


def group_tier(group_label: object) -> str:
    normalized = str(group_label or "").strip().upper()
    return normalized[0] if normalized in GROUP_LABELS else ""


def group_sort_key(group_label: object) -> tuple[int, str]:
    normalized = str(group_label or "").strip().upper()
    try:
        return (GROUP_LABELS.index(normalized), normalized)
    except ValueError:
        return (len(GROUP_LABELS), normalized)


def progress_status(tier: object, rank: int) -> str:
    normalized_tier = str(tier or "").strip().upper()
    if normalized_tier == "S":
        if 1 <= rank <= 2:
            return "直通"
        if 3 <= rank <= 11:
            return "晋级"
        if 12 <= rank <= 16:
            return "淘汰"
    if normalized_tier == "F":
        if rank == 1:
            return "直通"
        if 2 <= rank <= 8:
            return "晋级"
        if 9 <= rank <= 16:
            return "淘汰"
    return ""


def get_team_regular_season_group(team: dict[str, Any] | None) -> str:
    if not team:
        return ""
    if not is_target_scope(team.get("competition_name"), team.get("season_name")):
        return ""
    for item in team.get("stage_groups", []) or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("stage") or "").strip() != REGULAR_SEASON_STAGE:
            continue
        group_label = str(item.get("group_label") or "").strip().upper()
        return group_label if group_label in GROUP_LABELS else ""
    return ""


def build_team_group_map(data: dict[str, Any]) -> dict[str, str]:
    return {
        str(team.get("team_id") or ""): group_label
        for team in data.get("teams", [])
        if (group_label := get_team_regular_season_group(team))
    }


def build_placement_assignment_preview(data: dict[str, Any]) -> dict[str, Any]:
    placement_matches = [
        match
        for match in data.get("matches", [])
        if is_target_scope(get_match_competition_name(match), match.get("season"))
        and str(match.get("stage") or "").strip() == PLACEMENT_STAGE
        and bool(match.get("players"))
    ]
    scoped_data = {
        **data,
        "matches": placement_matches,
    }
    ranked_rows = [
        row
        for row in build_team_rows(
            scoped_data,
            TARGET_COMPETITION_NAME,
            TARGET_SEASON_NAME,
        )
        if int(row.get("matches_represented") or 0) > 0
    ]
    team_lookup = {
        str(team.get("team_id") or ""): team
        for team in data.get("teams", [])
    }
    rows: list[dict[str, Any]] = []
    for index, ranked_row in enumerate(ranked_rows, start=1):
        team_id = str(ranked_row.get("team_id") or "")
        rows.append(
            {
                "rank": index,
                "team_id": team_id,
                "team_name": str(ranked_row.get("name") or team_id),
                "points_total": round(float(ranked_row.get("points_earned_total") or 0.0), 2),
                "matches_represented": int(ranked_row.get("matches_represented") or 0),
                "win_rate": round(float(ranked_row.get("win_rate") or 0.0), 8),
                "stance_rate": round(float(ranked_row.get("stance_rate") or 0.0), 8),
                "current_group": get_team_regular_season_group(team_lookup.get(team_id)),
                "proposed_group": placement_group_for_rank(index),
            }
        )
    revision_source = [
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
    ]
    revision = hashlib.sha256(
        json.dumps(revision_source, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "competition_name": TARGET_COMPETITION_NAME,
        "season_name": TARGET_SEASON_NAME,
        "expected_team_count": EXPECTED_TEAM_COUNT,
        "team_count": len(rows),
        "ready": len(rows) == EXPECTED_TEAM_COUNT,
        "revision": revision,
        "rows": rows,
    }


def apply_placement_assignments(
    data: dict[str, Any],
    expected_revision: str,
) -> tuple[int, str]:
    preview = build_placement_assignment_preview(data)
    if not preview["ready"]:
        raise ValueError(
            f"定级赛必须恰好有 {EXPECTED_TEAM_COUNT} 支有效战队，当前为 {preview['team_count']} 支。"
        )
    if not expected_revision or expected_revision != preview["revision"]:
        raise ValueError("定级赛排行榜已变化，请刷新预览后重新确认分组。")
    assignment_by_team_id = {
        str(row["team_id"]): str(row["proposed_group"])
        for row in preview["rows"]
    }
    updated_count = 0
    for team in data.get("teams", []):
        team_id = str(team.get("team_id") or "")
        proposed_group = assignment_by_team_id.get(team_id)
        if not proposed_group:
            continue
        preserved_groups = [
            item
            for item in team.get("stage_groups", []) or []
            if isinstance(item, dict)
            and str(item.get("stage") or "").strip() != REGULAR_SEASON_STAGE
        ]
        team["stage_groups"] = [
            *preserved_groups,
            {"stage": REGULAR_SEASON_STAGE, "group_label": proposed_group},
        ]
        updated_count += 1
    return updated_count, str(preview["revision"])


def build_regular_season_team_leaderboards(
    data: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    team_lookup = {
        str(team.get("team_id") or ""): team
        for team in data.get("teams", [])
        if is_target_scope(team.get("competition_name"), team.get("season_name"))
    }
    team_group_map = build_team_group_map(data)
    boards: dict[str, dict[str, dict[str, Any]]] = {"S": {}, "F": {}}
    represented_players: dict[str, set[str]] = {}
    for team_id, group_label in team_group_map.items():
        tier = group_tier(group_label)
        team = team_lookup.get(team_id)
        if tier not in boards or not team:
            continue
        boards[tier][team_id] = {
            "team_id": team_id,
            "name": str(team.get("name") or team_id),
            "short_name": str(team.get("short_name") or team.get("name") or team_id),
            "logo": str(team.get("logo") or ""),
            "matches_represented": 0,
            "player_appearances": 0,
            "player_count": 0,
            "wins": 0,
            "losses": 0,
            "stance_calls": 0,
            "correct_stance_calls": 0,
            "points_earned_total": 0.0,
            "regular_season_group": group_label,
        }
        represented_players[team_id] = set()

    for match in data.get("matches", []):
        if not is_target_scope(get_match_competition_name(match), match.get("season")):
            continue
        if str(match.get("stage") or "").strip() != REGULAR_SEASON_STAGE:
            continue
        if not match.get("players") or is_team_score_excluded(match):
            continue
        represented_team_ids: set[str] = set()
        for participant in match.get("players", []):
            team_id = str(participant.get("team_id") or "")
            tier = group_tier(team_group_map.get(team_id))
            row = boards.get(tier, {}).get(team_id)
            if not row:
                continue
            represented_team_ids.add(team_id)
            row["player_appearances"] += 1
            row["wins"] += 1 if participant.get("result") == "win" else 0
            row["losses"] += 1 if participant.get("result") == "loss" else 0
            row["points_earned_total"] += float(participant.get("points_earned") or 0.0)
            player_id = str(participant.get("player_id") or "")
            if player_id:
                represented_players[team_id].add(player_id)
            stance_result = normalize_stance_result(participant)
            if stance_result != "none":
                row["stance_calls"] += 1
                if stance_result == "correct":
                    row["correct_stance_calls"] += 1
        for team_id in represented_team_ids:
            tier = group_tier(team_group_map.get(team_id))
            boards[tier][team_id]["matches_represented"] += 1

    result: dict[str, list[dict[str, Any]]] = {"S": [], "F": []}
    for tier in ("S", "F"):
        rows: list[dict[str, Any]] = []
        for team_id, row in boards[tier].items():
            appearances = int(row["player_appearances"])
            row["player_count"] = len(represented_players.get(team_id, set()))
            row["points_earned_total"] = round(float(row["points_earned_total"]), 2)
            row["win_rate"] = safe_rate(int(row["wins"]), appearances) if appearances else 0.0
            row["stance_rate"] = (
                safe_rate(int(row["correct_stance_calls"]), int(row["stance_calls"]))
                if row["stance_calls"]
                else 0.0
            )
            row["points_per_match"] = (
                round(row["points_earned_total"] / row["matches_represented"], 2)
                if row["matches_represented"]
                else 0.0
            )
            rows.append(row)
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
            row["progress_status"] = progress_status(tier, index)
        result[tier] = rows
    return result


def match_group_labels(
    data: dict[str, Any],
    match: dict[str, Any],
) -> list[str]:
    if not is_target_scope(get_match_competition_name(match), match.get("season")):
        return []
    if str(match.get("stage") or "").strip() != REGULAR_SEASON_STAGE:
        return []
    team_group_map = build_team_group_map(data)
    labels = {
        team_group_map.get(str(participant.get("team_id") or ""), "")
        for participant in match.get("players", [])
    }
    return sorted((label for label in labels if label), key=group_sort_key)
