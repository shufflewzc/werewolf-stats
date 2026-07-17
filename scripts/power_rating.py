from __future__ import annotations

import json
from typing import Any, Callable


POWER_RATING_OVERRIDES_KEY = "power_rating_overrides"
POWER_RATING_GRADES = ("S", "A", "B", "C", "D")


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _percentile_scores(rows: list[dict[str, Any]], metric_key: str) -> dict[str, float]:
    values = [_number(row.get(metric_key)) for row in rows]
    if not values:
        return {}
    if len(values) == 1:
        return {str(rows[0]["_rating_id"]): 100.0}
    result: dict[str, float] = {}
    for row, value in zip(rows, values):
        lower = sum(1 for candidate in values if candidate < value)
        equal = sum(1 for candidate in values if candidate == value)
        position = lower + max(0, equal - 1) / 2
        result[str(row["_rating_id"])] = position / (len(values) - 1) * 100.0
    return result


def grade_for_score(score: float) -> str:
    if score >= 90:
        return "S"
    if score >= 75:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def calculate_power_ratings(
    rows: list[dict[str, Any]],
    *,
    id_key: str,
    total_key: str,
    efficiency_key: str,
    win_rate_key: str,
    games_key: str,
) -> dict[str, dict[str, Any]]:
    prepared = [
        {**row, "_rating_id": str(row.get(id_key) or "")}
        for row in rows
        if str(row.get(id_key) or "").strip()
    ]
    total_scores = _percentile_scores(prepared, total_key)
    efficiency_scores = _percentile_scores(prepared, efficiency_key)
    win_rate_scores = _percentile_scores(prepared, win_rate_key)
    result: dict[str, dict[str, Any]] = {}
    for row in prepared:
        entity_id = str(row["_rating_id"])
        has_games = _number(row.get(games_key)) > 0
        score = (
            total_scores.get(entity_id, 0.0) * 0.5
            + efficiency_scores.get(entity_id, 0.0) * 0.25
            + win_rate_scores.get(entity_id, 0.0) * 0.25
        ) if has_games else 0.0
        score = round(score, 1)
        result[entity_id] = {
            "grade": grade_for_score(score),
            "auto_grade": grade_for_score(score),
            "class_name": f"grade-{grade_for_score(score).lower()}",
            "score": score,
            "source": "auto",
            "source_label": "系统评级",
        }
    return result


def parse_power_rating_overrides(raw_value: str | None) -> list[dict[str, str]]:
    try:
        parsed = json.loads(raw_value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def apply_power_rating_override(
    rating: dict[str, Any],
    overrides: list[dict[str, str]],
    *,
    entity_type: str,
    entity_id: str,
    competition_name: str,
    season_name: str,
) -> dict[str, Any]:
    matched = next(
        (
            item for item in reversed(overrides)
            if item.get("entity_type") == entity_type
            and item.get("entity_id") == entity_id
            and item.get("competition_name") == competition_name
            and item.get("season_name") == season_name
            and item.get("grade") in POWER_RATING_GRADES
        ),
        None,
    )
    if not matched:
        return rating
    return {
        **rating,
        "grade": matched["grade"],
        "class_name": f"grade-{matched['grade'].lower()}",
        "source": "manual",
        "source_label": "人工评级",
        "updated_by": matched.get("updated_by") or "管理员",
        "updated_at": matched.get("updated_at") or "",
    }


def save_power_rating_override(
    load_meta_value: Callable[[str], str | None],
    save_meta_value: Callable[[str, str], None],
    *,
    entity_type: str,
    entity_id: str,
    competition_name: str,
    season_name: str,
    grade: str,
    updated_by: str,
    updated_at: str,
) -> None:
    overrides = parse_power_rating_overrides(load_meta_value(POWER_RATING_OVERRIDES_KEY))
    overrides = [
        item for item in overrides
        if not (
            item.get("entity_type") == entity_type
            and item.get("entity_id") == entity_id
            and item.get("competition_name") == competition_name
            and item.get("season_name") == season_name
        )
    ]
    normalized_grade = str(grade or "").strip().upper()
    if normalized_grade in POWER_RATING_GRADES:
        overrides.append({
            "entity_type": entity_type,
            "entity_id": entity_id,
            "competition_name": competition_name,
            "season_name": season_name,
            "grade": normalized_grade,
            "updated_by": updated_by,
            "updated_at": updated_at,
        })
    save_meta_value(POWER_RATING_OVERRIDES_KEY, json.dumps(overrides, ensure_ascii=False))
