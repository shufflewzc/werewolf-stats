from __future__ import annotations

import hashlib
import json
from datetime import date

import web_app as legacy
from season_grouping import (
    match_group_labels,
    match_team_group_map,
    team_group_badge_for_stage,
)

Any = legacy.Any
account_role_label = legacy.account_role_label
build_player_rows = legacy.build_player_rows
MATCH_SCORE_COMPONENT_FIELDS = legacy.MATCH_SCORE_COMPONENT_FIELDS
RequestContext = legacy.RequestContext
RESULT_OPTIONS = legacy.RESULT_OPTIONS
STANCE_OPTIONS = legacy.STANCE_OPTIONS
STAGE_OPTIONS = legacy.STAGE_OPTIONS
build_match_day_path = legacy.build_match_day_path
build_match_next_path = legacy.build_match_next_path
build_scoped_path = legacy.build_scoped_path
can_manage_matches = legacy.can_manage_matches
escape = legacy.escape
form_value = legacy.form_value
get_match_by_id = legacy.get_match_by_id
get_match_competition_name = legacy.get_match_competition_name
get_match_score_model_label = legacy.get_match_score_model_label
format_pct = legacy.format_pct
get_player_dimension_history = legacy.get_player_dimension_history
is_admin_user = legacy.is_admin_user
is_placeholder_match = legacy.is_placeholder_match
layout = legacy.layout
load_validated_data = legacy.load_validated_data
normalize_match_score_model = legacy.normalize_match_score_model
normalize_score_breakdown = legacy.normalize_score_breakdown
normalize_stance_result = legacy.normalize_stance_result
quote = legacy.quote
resolve_scoring_rule_for_scope = legacy.resolve_scoring_rule_for_scope
resolve_stage_label_for_scope = legacy.resolve_stage_label_for_scope
scoring_rule_component_fields = legacy.scoring_rule_component_fields
start_response_json = legacy.start_response_json
to_chinese_camp = legacy.to_chinese_camp
urlencode = legacy.urlencode
uses_structured_score_model = legacy.uses_structured_score_model
safe_rate = legacy.safe_rate
summarize_dimension_rows = legacy.summarize_dimension_rows

PREDICTION_BUCKETS = [
    ("lt_2", "小于2分", "<", 2.0),
    ("lt_5", "小于5分", "<", 5.0),
    ("lt_7", "小于7分", "<", 7.0),
    ("gt_7", "大于7分", ">", 7.0),
    ("gt_12", "大于12分", ">", 12.0),
    ("gt_14_5", "大于14.5分", ">", 14.5),
]

WIN_RESULT_POINTS = 5.0
PREDICTION_SETTING_CAMPS = [
    ("werewolves", "狼人"),
    ("villagers", "好人"),
    ("third_party", "第三方"),
]

PREDICTION_DAY_SCENARIOS_KEY = "prediction_day_scenarios"
PREDICTION_DAY_SCENARIO_VERSION = "prediction_day_scenario_v1"


def prediction_day_scenario_key(
    competition_name: str,
    season_name: str,
    played_on: str,
) -> str:
    return "\x1f".join(
        str(value or "").strip()
        for value in (competition_name, season_name, played_on)
    )


def _stable_scenario_player_id(
    competition_name: str,
    season_name: str,
    played_on: str,
    player_name: str,
    seat: int,
) -> str:
    raw_value = "\x1f".join(
        [competition_name, season_name, played_on, player_name.casefold(), str(seat)]
    )
    digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()[:16]
    return f"scenario-{digest}"


def normalize_prediction_day_scenario(
    raw_item: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(raw_item, dict):
        return None
    competition_name = str(raw_item.get("competition_name") or "").strip()
    season_name = str(raw_item.get("season_name") or "").strip()
    played_on = str(raw_item.get("played_on") or "").strip()
    if not competition_name or not season_name or not played_on:
        return None
    roster = []
    for index, raw_row in enumerate(raw_item.get("roster") or []):
        if not isinstance(raw_row, dict):
            continue
        player_name = str(raw_row.get("player_name") or "").strip()
        team_name = str(raw_row.get("team_name") or "").strip()
        if not player_name or not team_name:
            continue
        override = raw_row.get("manual_total_override")
        if override in (None, ""):
            normalized_override = None
        else:
            try:
                normalized_override = max(-10.0, min(30.0, round(float(override) * 2.0) / 2.0))
            except (TypeError, ValueError):
                normalized_override = None
        seat = index + 1
        roster.append(
            {
                "seat": seat,
                "player_id": str(raw_row.get("player_id") or "").strip(),
                "scenario_player_id": str(raw_row.get("scenario_player_id") or "").strip()
                or _stable_scenario_player_id(
                    competition_name, season_name, played_on, player_name, seat
                ),
                "player_name": player_name,
                "team_id": str(raw_row.get("team_id") or "").strip(),
                "team_name": team_name,
                "manual_total_override": normalized_override,
            }
        )
    return {
        "version": str(raw_item.get("version") or PREDICTION_DAY_SCENARIO_VERSION),
        "competition_name": competition_name,
        "season_name": season_name,
        "played_on": played_on,
        "published": bool(raw_item.get("published", True)),
        "roster": roster,
        "updated_by": str(raw_item.get("updated_by") or "").strip(),
        "updated_at": str(raw_item.get("updated_at") or "").strip(),
        "published_at": str(raw_item.get("published_at") or "").strip(),
    }


def load_prediction_day_scenarios() -> dict[str, dict[str, Any]]:
    raw_value = legacy.load_meta_value(PREDICTION_DAY_SCENARIOS_KEY) or ""
    if not raw_value.strip():
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    result = {}
    for raw_item in parsed.values():
        item = normalize_prediction_day_scenario(raw_item)
        if not item:
            continue
        result[
            prediction_day_scenario_key(
                item["competition_name"], item["season_name"], item["played_on"]
            )
        ] = item
    return result


def save_prediction_day_scenarios(
    scenarios: dict[str, dict[str, Any]],
) -> None:
    clean_payload = {}
    for raw_item in scenarios.values():
        item = normalize_prediction_day_scenario(raw_item)
        if not item:
            continue
        key = prediction_day_scenario_key(
            item["competition_name"], item["season_name"], item["played_on"]
        )
        clean_payload[key] = item
    legacy.save_meta_value(
        PREDICTION_DAY_SCENARIOS_KEY,
        json.dumps(clean_payload, ensure_ascii=False, sort_keys=True),
    )
    legacy.invalidate_prediction_api_cache()


def _is_completed_prediction_match(match: dict[str, Any], current_match_id: str) -> bool:
    if str(match.get("match_id") or "") == current_match_id:
        return False
    if is_placeholder_match(match):
        return False
    participants = match.get("players", [])
    if not participants:
        return False
    if any(float(item.get("points_earned") or 0.0) > 0 for item in participants):
        return True
    return bool(
        str(match.get("mvp_player_id") or "").strip()
        or str(match.get("svp_player_id") or "").strip()
        or str(match.get("scapegoat_player_id") or "").strip()
    )


def _collect_player_point_samples(
    data: dict[str, Any],
    player_id: str,
    competition_name: str,
    season_name: str,
    current_match_id: str,
) -> tuple[list[float], list[float]]:
    current_season_points: list[float] = []
    other_season_points: list[float] = []
    for match in data.get("matches", []):
        if not _is_completed_prediction_match(match, current_match_id):
            continue
        match_competition = get_match_competition_name(match)
        match_season = str(match.get("season") or "").strip()
        for participant in match.get("players", []):
            if str(participant.get("player_id") or "").strip() != player_id:
                continue
            points = float(participant.get("points_earned") or 0.0)
            if match_competition == competition_name and match_season == season_name:
                current_season_points.append(points)
            else:
                other_season_points.append(points)
            break
    return current_season_points, other_season_points


def _is_win_result(participant: dict[str, Any]) -> bool:
    return str(participant.get("result") or "").strip() == "win"


def _base_points_without_result(participant: dict[str, Any]) -> float:
    points = float(participant.get("points_earned") or 0.0)
    result_points = float(participant.get("result_points") or 0.0)
    if result_points:
        return max(0.0, points - result_points)
    if _is_win_result(participant):
        return max(0.0, points - WIN_RESULT_POINTS)
    return max(0.0, points)


def _new_win_stats() -> dict[str, float]:
    return {"games": 0.0, "wins": 0.0}


def _add_win_stat(stats: dict[str, float], participant: dict[str, Any]) -> None:
    stats["games"] = float(stats.get("games") or 0.0) + 1.0
    if _is_win_result(participant):
        stats["wins"] = float(stats.get("wins") or 0.0) + 1.0


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _smoothed_rate(stats: dict[str, float], prior: float = 0.5, prior_games: float = 4.0) -> float:
    games = float(stats.get("games") or 0.0)
    wins = float(stats.get("wins") or 0.0)
    return (wins + prior * prior_games) / (games + prior_games) if games + prior_games > 0 else prior


def _sample_reliability(games: float, full_games: float) -> float:
    if full_games <= 0:
        return 0.0
    return max(0.0, min(1.0, float(games or 0.0) / full_games))


def _weighted_average(items: list[tuple[float, float]]) -> float:
    valid_items = [(value, weight) for value, weight in items if weight > 0]
    total_weight = sum(weight for _, weight in valid_items)
    if total_weight <= 0:
        return 0.0
    return sum(value * weight for value, weight in valid_items) / total_weight


def _collect_prediction_context(
    data: dict[str, Any],
    player_id: str,
    competition_name: str,
    season_name: str,
    current_match_id: str,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "current_base_points": [],
        "other_base_points": [],
        "event_overall": _new_win_stats(),
        "event_by_camp": {},
        "player_overall": _new_win_stats(),
        "player_current": _new_win_stats(),
        "player_by_camp": {},
    }
    for match in data.get("matches", []):
        if not _is_completed_prediction_match(match, current_match_id):
            continue
        match_competition = get_match_competition_name(match)
        match_season = str(match.get("season") or "").strip()
        is_current_scope = match_competition == competition_name and match_season == season_name
        for participant in match.get("players", []):
            camp = str(participant.get("camp") or "").strip()
            if is_current_scope:
                _add_win_stat(context["event_overall"], participant)
                if camp:
                    camp_stats = context["event_by_camp"].setdefault(camp, _new_win_stats())
                    _add_win_stat(camp_stats, participant)
            if str(participant.get("player_id") or "").strip() != player_id:
                continue
            if is_current_scope:
                context["current_base_points"].append(_base_points_without_result(participant))
                _add_win_stat(context["player_current"], participant)
            else:
                context["other_base_points"].append(_base_points_without_result(participant))
            _add_win_stat(context["player_overall"], participant)
            if camp:
                player_camp_stats = context["player_by_camp"].setdefault(camp, _new_win_stats())
                _add_win_stat(player_camp_stats, participant)
    return context


def _empty_prediction_context() -> dict[str, Any]:
    return {
        "current_points": [],
        "other_points": [],
        "current_base_points": [],
        "other_base_points": [],
        "event_overall": _new_win_stats(),
        "event_by_camp": {},
        "player_overall": _new_win_stats(),
        "player_current": _new_win_stats(),
        "player_by_camp": {},
    }


def _clone_win_stats(stats: dict[str, float]) -> dict[str, float]:
    return {"games": float(stats.get("games") or 0.0), "wins": float(stats.get("wins") or 0.0)}


def _prediction_history_index(
    data: dict[str, Any],
    competition_name: str,
    season_name: str,
    current_match_id: str,
) -> dict[str, dict[str, Any]]:
    event_overall = _new_win_stats()
    event_by_camp: dict[str, dict[str, float]] = {}
    by_player: dict[str, dict[str, Any]] = {}
    for match in data.get("matches", []):
        if not _is_completed_prediction_match(match, current_match_id):
            continue
        match_competition = get_match_competition_name(match)
        match_season = str(match.get("season") or "").strip()
        is_current_scope = match_competition == competition_name and match_season == season_name
        for participant in match.get("players", []):
            camp = str(participant.get("camp") or "").strip()
            if is_current_scope:
                _add_win_stat(event_overall, participant)
                if camp:
                    _add_win_stat(event_by_camp.setdefault(camp, _new_win_stats()), participant)
            player_id = str(participant.get("player_id") or "").strip()
            if not player_id:
                continue
            context = by_player.setdefault(player_id, _empty_prediction_context())
            points = float(participant.get("points_earned") or 0.0)
            if is_current_scope:
                context["current_points"].append(points)
                context["current_base_points"].append(_base_points_without_result(participant))
                _add_win_stat(context["player_current"], participant)
            else:
                context["other_points"].append(points)
                context["other_base_points"].append(_base_points_without_result(participant))
            _add_win_stat(context["player_overall"], participant)
            if camp:
                _add_win_stat(context["player_by_camp"].setdefault(camp, _new_win_stats()), participant)
    for context in by_player.values():
        context["event_overall"] = _clone_win_stats(event_overall)
        context["event_by_camp"] = {
            camp: _clone_win_stats(stats)
            for camp, stats in event_by_camp.items()
        }
    by_player["__event__"] = {
        "event_overall": _clone_win_stats(event_overall),
        "event_by_camp": {
            camp: _clone_win_stats(stats)
            for camp, stats in event_by_camp.items()
        },
    }
    return by_player


def _prediction_context_from_index(index: dict[str, dict[str, Any]], player_id: str) -> dict[str, Any]:
    context = index.get(player_id)
    if context is not None:
        return context
    event_context = index.get("__event__", {})
    context = _empty_prediction_context()
    context["event_overall"] = _clone_win_stats(event_context.get("event_overall") or {})
    context["event_by_camp"] = {
        camp: _clone_win_stats(stats)
        for camp, stats in (event_context.get("event_by_camp") or {}).items()
    }
    return context


def _estimate_win_probability(
    context: dict[str, Any],
    participant_camp: str,
    current_win_rate: float,
    all_win_rate: float,
    dimension: dict[str, float],
    settings: dict[str, Any],
) -> float:
    camp_prior = settings.get("camp_win_rate_priors", {}).get(participant_camp, 0.5)
    event_overall_stats = context["event_overall"]
    event_overall_rate = _smoothed_rate(event_overall_stats, prior=0.5, prior_games=8.0)
    camp_stats = context["event_by_camp"].get(participant_camp) or _new_win_stats()
    event_camp_prior = (camp_prior * 0.65) + (event_overall_rate * 0.35)
    event_camp_rate = _smoothed_rate(camp_stats, prior=event_camp_prior, prior_games=8.0)

    player_current_stats = context["player_current"]
    player_overall_stats = context["player_overall"]
    player_camp_stats = context["player_by_camp"].get(participant_camp) or _new_win_stats()
    player_current_rate = (
        float(current_win_rate)
        if float(player_current_stats.get("games") or 0.0) > 0
        else _smoothed_rate(player_overall_stats, prior=event_camp_rate, prior_games=4.0)
    )
    if all_win_rate > 0 and float(player_overall_stats.get("games") or 0.0) <= 0:
        player_current_rate = all_win_rate
    player_camp_rate = _smoothed_rate(player_camp_stats, prior=event_camp_rate, prior_games=4.0)
    dimension_rate = float(dimension.get("win_rate") or 0.0) if float(dimension.get("games") or 0.0) > 0 else event_camp_rate

    if participant_camp:
        items = [
            (camp_prior, 0.18),
            (event_camp_rate, 0.32 * max(0.45, _sample_reliability(camp_stats.get("games") or 0.0, 12.0))),
            (player_camp_rate, 0.30 * max(0.35, _sample_reliability(player_camp_stats.get("games") or 0.0, 6.0))),
            (player_current_rate, 0.20 * max(0.45, _sample_reliability(player_current_stats.get("games") or 0.0, 8.0))),
            (dimension_rate, 0.10 * max(0.35, _sample_reliability(dimension.get("games") or 0.0, 8.0))),
        ]
    else:
        items = [
            (event_overall_rate, 0.35),
            (player_current_rate, 0.40),
            (dimension_rate, 0.25),
        ]
    win_rate_floor = settings.get("camp_win_rate_floors", {}).get(participant_camp, 0.05)
    return max(win_rate_floor, min(0.99, _weighted_average(items)))


def _estimate_base_points(
    context: dict[str, Any],
    dimension: dict[str, float],
    all_avg: float,
    all_win_rate: float,
    expected_win_probability: float,
    fallback_anchor: float,
) -> float:
    current_base_avg = _average(context["current_base_points"])
    other_base_avg = _average(context["other_base_points"])
    dimension_base_avg = max(0.0, float(dimension.get("avg_points") or 0.0) - WIN_RESULT_POINTS * float(dimension.get("win_rate") or 0.0))
    all_base_avg = max(0.0, float(all_avg or 0.0) - WIN_RESULT_POINTS * float(all_win_rate or expected_win_probability))
    candidates: list[tuple[float, float]] = []
    if context["current_base_points"]:
        candidates.append((current_base_avg, 1.0))
    if dimension_base_avg > 0:
        candidates.append((dimension_base_avg, 0.75))
    if all_base_avg > 0:
        candidates.append((all_base_avg, 0.45))
    if context["other_base_points"]:
        candidates.append((other_base_avg, 0.35))
    if candidates:
        return _weighted_average(candidates)
    return max(0.0, fallback_anchor - WIN_RESULT_POINTS * expected_win_probability)


def _find_player_row(
    data: dict[str, Any],
    player_id: str,
    competition_name: str | None,
    season_name: str | None,
) -> dict[str, Any] | None:
    rows = build_player_rows(data, competition_name, season_name)
    return next((row for row in rows if row.get("player_id") == player_id and int(row.get("games_played") or 0) > 0), None)


def _build_dimension_anchor(
    data: dict[str, Any],
    player_id: str,
    competition_name: str,
    season_name: str,
) -> dict[str, float]:
    current_rows = [
        row
        for row in get_player_dimension_history(data, player_id, competition_name, season_name)
        if str(row.get("season_name") or "").strip() == season_name
    ]
    if not current_rows:
        return {"games": 0.0, "avg_points": 0.0, "win_rate": 0.0, "mvp_rate": 0.0}
    summary = summarize_dimension_rows(current_rows)
    games = float(summary.get("games_played") or 0.0)
    return {
        "games": games,
        "avg_points": safe_rate(float(summary.get("daily_points") or 0.0), games),
        "win_rate": safe_rate(float(summary.get("wins") or 0.0), games),
        "mvp_rate": safe_rate(float(summary.get("mvp_count") or 0.0), games),
    }


def _dimension_anchor_from_rows(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {"games": 0.0, "avg_points": 0.0, "win_rate": 0.0, "mvp_rate": 0.0}
    summary = summarize_dimension_rows(rows)
    games = float(summary.get("games_played") or 0.0)
    return {
        "games": games,
        "avg_points": safe_rate(float(summary.get("daily_points") or 0.0), games),
        "win_rate": safe_rate(float(summary.get("wins") or 0.0), games),
        "mvp_rate": safe_rate(float(summary.get("mvp_count") or 0.0), games),
    }


def build_score_prediction_context_cache(
    data: dict[str, Any],
    competition_name: str,
    season_name: str,
    match_ids: list[str],
) -> dict[str, Any]:
    current_rows = {
        row.get("player_id"): row
        for row in build_player_rows(data, competition_name, season_name)
        if int(row.get("games_played") or 0) > 0
    }
    all_rows = {
        row.get("player_id"): row
        for row in build_player_rows(data, None, None)
        if int(row.get("games_played") or 0) > 0
    }
    dimension_rows_by_player: dict[str, list[dict[str, Any]]] = {}
    for row in data.get("season_player_dimension_stats", []):
        if row.get("competition_name") != competition_name or row.get("season_name") != season_name:
            continue
        player_id = str(row.get("player_id") or "").strip()
        if player_id:
            dimension_rows_by_player.setdefault(player_id, []).append(row)
    dimensions = {
        player_id: _dimension_anchor_from_rows(rows)
        for player_id, rows in dimension_rows_by_player.items()
    }
    return {
        "player_lookup": {player["player_id"]: player for player in data.get("players", [])},
        "team_lookup": {team["team_id"]: team for team in data.get("teams", [])},
        "settings": legacy.load_prediction_model_settings(),
        "manual_predictions": load_manual_score_predictions(),
        "current_rows": current_rows,
        "all_rows": all_rows,
        "dimensions": dimensions,
        "history_indexes": {
            match_id: _prediction_history_index(data, competition_name, season_name, match_id)
            for match_id in match_ids
        },
    }


def _weighted_probability(samples: list[tuple[float, float]], operator: str, threshold: float) -> float:
    total_weight = sum(weight for _, weight in samples)
    if total_weight <= 0:
        return 0.0
    if operator == "<":
        matched = sum(weight for value, weight in samples if value < threshold)
    else:
        matched = sum(weight for value, weight in samples if value > threshold)
    return matched / total_weight


def score_prediction_labels() -> list[dict[str, str]]:
    return [{"key": key, "label": label} for key, label, _, _ in PREDICTION_BUCKETS]


def empty_manual_prediction() -> dict[str, float | None]:
    return {key: None for key, _, _, _ in PREDICTION_BUCKETS}


def normalize_manual_prediction(raw_item: dict[str, Any] | None) -> dict[str, float | None]:
    result = empty_manual_prediction()
    if not isinstance(raw_item, dict):
        return result
    for key, _, _, _ in PREDICTION_BUCKETS:
        raw_value = raw_item.get(key)
        if raw_value in (None, ""):
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if value > 1:
            value = value / 100.0
        result[key] = max(0.0, min(1.0, value))
    return result


def load_manual_score_predictions() -> dict[str, dict[str, dict[str, float | None]]]:
    raw_value = legacy.load_meta_value("manual_score_predictions") or ""
    if not raw_value.strip():
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    result: dict[str, dict[str, dict[str, float | None]]] = {}
    if not isinstance(parsed, dict):
        return result
    for match_id, player_items in parsed.items():
        if not isinstance(player_items, dict):
            continue
        normalized_match_id = str(match_id or "").strip()
        if not normalized_match_id:
            continue
        result[normalized_match_id] = {}
        for player_id, values in player_items.items():
            normalized_player_id = str(player_id or "").strip()
            if not normalized_player_id:
                continue
            result[normalized_match_id][normalized_player_id] = normalize_manual_prediction(values)
        if not result[normalized_match_id]:
            result.pop(normalized_match_id, None)
    return result


def save_manual_score_predictions(payload: dict[str, dict[str, dict[str, float | None]]]) -> None:
    clean_payload: dict[str, dict[str, dict[str, float]]] = {}
    for match_id, player_items in payload.items():
        normalized_match_id = str(match_id or "").strip()
        if not normalized_match_id or not isinstance(player_items, dict):
            continue
        clean_payload[normalized_match_id] = {}
        for player_id, values in player_items.items():
            normalized_player_id = str(player_id or "").strip()
            normalized_values = normalize_manual_prediction(values)
            clean_values = {
                key: float(value)
                for key, value in normalized_values.items()
                if value is not None
            }
            if normalized_player_id and clean_values:
                clean_payload[normalized_match_id][normalized_player_id] = clean_values
        if not clean_payload[normalized_match_id]:
            clean_payload.pop(normalized_match_id, None)
    legacy.save_meta_value("manual_score_predictions", json.dumps(clean_payload, ensure_ascii=False))
    legacy.invalidate_prediction_api_cache()


def apply_manual_score_predictions(
    predictions: list[dict[str, Any]],
    match_id: str,
    all_manual: dict[str, dict[str, dict[str, float | None]]] | None = None,
) -> list[dict[str, Any]]:
    manual_by_player = (all_manual if all_manual is not None else load_manual_score_predictions()).get(match_id, {})
    for item in predictions:
        manual_values = normalize_manual_prediction(manual_by_player.get(str(item.get("player_id") or "")))
        manual_payload = []
        for key, label, _, _ in PREDICTION_BUCKETS:
            value = manual_values.get(key)
            manual_payload.append(
                {
                    "key": key,
                    "label": label,
                    "value": value,
                    "display": format_pct(float(value)) if value is not None else "未填写",
                }
            )
        item["manual_probabilities"] = manual_payload
    return predictions


def build_match_score_predictions(
    data: dict[str, Any],
    match: dict[str, Any],
    competition_name: str,
    season_name: str,
    selected_region: str | None,
    selected_series_slug: str | None,
    context_cache: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    current_match_id = str(match.get("match_id") or "")
    if context_cache is None:
        context_cache = build_score_prediction_context_cache(data, competition_name, season_name, [current_match_id])
    player_lookup = context_cache.get("player_lookup") or {player["player_id"]: player for player in data.get("players", [])}
    team_lookup = context_cache.get("team_lookup") or {team["team_id"]: team for team in data.get("teams", [])}
    settings = context_cache.get("settings") or legacy.load_prediction_model_settings()
    current_rows = context_cache.get("current_rows") or {}
    all_rows = context_cache.get("all_rows") or {}
    dimensions = context_cache.get("dimensions") or {}
    history_indexes = context_cache.get("history_indexes") or {}
    history_index = history_indexes.get(current_match_id)
    if history_index is None:
        history_index = _prediction_history_index(data, competition_name, season_name, current_match_id)
    predictions: list[dict[str, Any]] = []
    for participant in sorted(match.get("players", []), key=lambda item: int(item.get("seat") or 0)):
        player_id = str(participant.get("player_id") or "").strip()
        if not player_id:
            continue
        prediction_context = _prediction_context_from_index(history_index, player_id)
        current_points = prediction_context.get("current_points") or []
        other_points = prediction_context.get("other_points") or []
        player_row = current_rows.get(player_id)
        all_row = all_rows.get(player_id)
        dimension = dimensions.get(player_id) or {"games": 0.0, "avg_points": 0.0, "win_rate": 0.0, "mvp_rate": 0.0}
        weighted_samples: list[tuple[float, float]] = [(value, 1.0) for value in current_points]
        weighted_samples.extend((value, 0.45) for value in other_points)
        current_avg = (
            float(player_row.get("average_points") or 0.0)
            if player_row
            else (sum(current_points) / len(current_points) if current_points else 0.0)
        )
        current_win_rate = float(player_row.get("win_rate") or 0.0) if player_row else 0.0
        all_avg = float(all_row.get("average_points") or 0.0) if all_row else 0.0
        all_win_rate = float(all_row.get("win_rate") or 0.0) if all_row else 0.0
        anchor_candidates = [value for value in [current_avg, dimension["avg_points"], all_avg] if value > 0]
        anchor = sum(anchor_candidates) / len(anchor_candidates) if anchor_candidates else 7.0
        participant_camp = str(participant.get("camp") or "").strip()
        expected_win_probability = _estimate_win_probability(
            prediction_context,
            participant_camp,
            current_win_rate,
            all_win_rate,
            dimension,
            settings,
        )
        base_points_anchor = _estimate_base_points(
            prediction_context,
            dimension,
            all_avg,
            all_win_rate,
            expected_win_probability,
            anchor,
        )
        structured_anchor = max(
            0.0,
            base_points_anchor
            + WIN_RESULT_POINTS * expected_win_probability
            + float(dimension.get("mvp_rate") or 0.0) * 1.5,
        )
        camp_base_floor = settings.get("camp_base_point_floors", {}).get(participant_camp, 0.50)
        camp_floor_anchor = camp_base_floor + WIN_RESULT_POINTS * expected_win_probability
        structured_anchor = max(structured_anchor, camp_floor_anchor)
        adjusted_anchor = (structured_anchor * float(settings.get("score_uplift") or 1.0)) + float(settings.get("score_bonus") or 0.0)
        camp_cap = settings.get("camp_expected_point_caps", {}).get(participant_camp)
        if camp_cap is not None:
            adjusted_anchor = min(adjusted_anchor, camp_cap)
        pseudo_weight = max(0.8, min(3.0, (dimension["games"] * 0.18) + (1.0 if player_row else 0.0)))
        weighted_samples.append((adjusted_anchor, pseudo_weight))
        if not current_points and other_points:
            weighted_samples.append((sum(other_points) / len(other_points), 1.1))
        probabilities = [
            {
                "key": key,
                "label": label,
                "value": round(_weighted_probability(weighted_samples, operator, threshold), 4),
                "display": format_pct(_weighted_probability(weighted_samples, operator, threshold)),
            }
            for key, label, operator, threshold in PREDICTION_BUCKETS
        ]
        sample_weight = sum(weight for _, weight in weighted_samples)
        if len(current_points) >= 6:
            confidence = "较高"
        elif len(current_points) >= 3 or sample_weight >= 4:
            confidence = "中等"
        else:
            confidence = "偏低"
        predictions.append(
            {
                "seat": int(participant.get("seat") or 0),
                "player_id": player_id,
                "player_name": player_lookup.get(player_id, {}).get("display_name") or player_id,
                "player_href": build_scoped_path(f"/players/{player_id}", competition_name, season_name, selected_region, selected_series_slug),
                "team_name": team_lookup.get(str(participant.get("team_id") or ""), {}).get("name") or str(participant.get("team_id") or ""),
                "current_samples": len(current_points),
                "reference_samples": len(other_points),
                "dimension_games": int(dimension["games"]),
                "expected_points": f"{adjusted_anchor:.2f}",
                "expected_win_rate": format_pct(expected_win_probability),
                "base_points": f"{base_points_anchor:.2f}",
                "prediction_model": settings.get("model_version") or "result_weighted",
                "win_rate": format_pct(current_win_rate),
                "confidence": confidence,
                "probabilities": probabilities,
            }
        )
    return apply_manual_score_predictions(predictions, current_match_id, context_cache.get("manual_predictions"))


def _format_manual_input_value(value: float | None) -> str:
    if value is None:
        return ""
    return f"{float(value) * 100:.1f}".rstrip("0").rstrip(".")


def _format_setting_number(value: Any, *, percent: bool = False) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if percent:
        number *= 100.0
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _parse_setting_number(
    raw_value: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
    percent: bool = False,
) -> float:
    try:
        value = float(str(raw_value or "").strip())
    except ValueError:
        value = default * 100.0 if percent else default
    if percent:
        value = value / 100.0
    return max(minimum, min(maximum, value))


def _prediction_settings_from_form(ctx: RequestContext, current_settings: dict[str, Any]) -> dict[str, Any]:
    settings = {
        "model_version": "result_weighted_custom",
        "jcds_three_game_enabled": form_value(
            ctx.form, "jcds_three_game_enabled"
        ).strip()
        == "1",
        "score_uplift": _parse_setting_number(
            form_value(ctx.form, "score_uplift"),
            float(current_settings.get("score_uplift") or 1.0),
            minimum=0.5,
            maximum=1.5,
        ),
        "score_bonus": _parse_setting_number(
            form_value(ctx.form, "score_bonus"),
            float(current_settings.get("score_bonus") or 0.0),
            minimum=-3.0,
            maximum=3.0,
        ),
        "camp_win_rate_priors": {},
        "camp_win_rate_floors": {},
        "camp_base_point_floors": {},
        "camp_expected_point_caps": {},
        "day_total": {},
    }
    for camp, _ in PREDICTION_SETTING_CAMPS:
        settings["camp_win_rate_priors"][camp] = _parse_setting_number(
            form_value(ctx.form, f"{camp}_win_prior"),
            float(current_settings.get("camp_win_rate_priors", {}).get(camp, 0.5)),
            minimum=0.0,
            maximum=1.0,
            percent=True,
        )
        settings["camp_win_rate_floors"][camp] = _parse_setting_number(
            form_value(ctx.form, f"{camp}_win_floor"),
            float(current_settings.get("camp_win_rate_floors", {}).get(camp, 0.0)),
            minimum=0.0,
            maximum=1.0,
            percent=True,
        )
        settings["camp_base_point_floors"][camp] = _parse_setting_number(
            form_value(ctx.form, f"{camp}_base_floor"),
            float(current_settings.get("camp_base_point_floors", {}).get(camp, 0.0)),
            minimum=0.0,
            maximum=20.0,
        )
    settings["camp_expected_point_caps"]["werewolves"] = _parse_setting_number(
        form_value(ctx.form, "werewolves_point_cap"),
        float(current_settings.get("camp_expected_point_caps", {}).get("werewolves", 5.2)),
        minimum=0.0,
        maximum=50.0,
    )
    current_day = current_settings.get("day_total", {})
    for key, default, minimum, maximum in [
        ("elite_threshold", 12.0, 0.0, 50.0),
        ("elite_min", 12.0, 0.0, 50.0),
        ("elite_max", 12.6, 0.0, 50.0),
        ("elite_anchor", 10.5, 0.0, 50.0),
        ("elite_slope", 0.55, 0.0, 2.0),
        ("middle_min", 7.05, 0.0, 50.0),
        ("middle_slope", 0.55, 0.0, 2.0),
        ("main_min", 5.05, 0.0, 50.0),
        ("main_max", 6.95, 0.0, 50.0),
        ("main_slope", 0.45, 0.0, 2.0),
    ]:
        settings["day_total"][key] = _parse_setting_number(
            form_value(ctx.form, key),
            float(current_day.get(key, default)),
            minimum=minimum,
            maximum=maximum,
        )
    settings["day_total"]["middle_slots"] = int(
        _parse_setting_number(
            form_value(ctx.form, "middle_slots"),
            float(current_day.get("middle_slots", 4)),
            minimum=0,
            maximum=12,
        )
    )
    raw_caps = form_value(ctx.form, "middle_caps")
    parsed_caps = []
    for value in raw_caps.replace("，", ",").split(","):
        value = value.strip()
        if not value:
            continue
        parsed_caps.append(_parse_setting_number(value, 8.2, minimum=0.0, maximum=50.0))
    settings["day_total"]["middle_caps"] = parsed_caps or list(current_day.get("middle_caps") or [11.4, 10.2, 9.2, 8.2])
    return settings


def _prediction_model_settings_form_html(settings: dict[str, Any], can_edit: bool) -> str:
    day = settings.get("day_total", {})
    camp_rows = []
    for camp, label in PREDICTION_SETTING_CAMPS:
        camp_rows.append(
            f"""
            <tr>
              <td>{escape(label)}</td>
              <td><input class="form-control form-control-sm" type="number" step="0.1" min="0" max="100" name="{camp}_win_prior" value="{escape(_format_setting_number(settings.get('camp_win_rate_priors', {}).get(camp), percent=True))}" {'readonly' if not can_edit else ''}></td>
              <td><input class="form-control form-control-sm" type="number" step="0.1" min="0" max="100" name="{camp}_win_floor" value="{escape(_format_setting_number(settings.get('camp_win_rate_floors', {}).get(camp), percent=True))}" {'readonly' if not can_edit else ''}></td>
              <td><input class="form-control form-control-sm" type="number" step="0.01" min="0" name="{camp}_base_floor" value="{escape(_format_setting_number(settings.get('camp_base_point_floors', {}).get(camp)))}" {'readonly' if not can_edit else ''}></td>
            </tr>
            """
        )
    middle_caps_text = ", ".join(_format_setting_number(value) for value in day.get("middle_caps", []))
    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">模型参数</h2>
          <p class="section-copy mb-0">这里控制小程序比赛日预测分布。修改后无需发版，前台接口会直接读取最新参数。</p>
        </div>
        <span class="chip">当前模型 {escape(str(settings.get('model_version') or 'result_weighted'))}</span>
      </div>
      <form method="post" action="/prediction-admin">
        <input type="hidden" name="action" value="save_model_settings">
        <div class="form-check form-switch mb-3">
          <input class="form-check-input" type="checkbox" role="switch" id="jcds_three_game_enabled" name="jcds_three_game_enabled" value="1" {'checked' if settings.get('jcds_three_game_enabled', True) else ''} {'disabled' if not can_edit else ''}>
          <label class="form-check-label fw-semibold" for="jcds_three_game_enabled">启用京城大师赛三局模型（关闭后立即回退原预测模型）</label>
        </div>
        <div class="row g-3">
          <div class="col-12 col-lg-3">
            <label class="form-label">整体倍率</label>
            <input class="form-control" type="number" step="0.01" min="0.5" max="1.5" name="score_uplift" value="{escape(_format_setting_number(settings.get('score_uplift')))}" {'readonly' if not can_edit else ''}>
          </div>
          <div class="col-12 col-lg-3">
            <label class="form-label">整体加分</label>
            <input class="form-control" type="number" step="0.01" min="-3" max="3" name="score_bonus" value="{escape(_format_setting_number(settings.get('score_bonus')))}" {'readonly' if not can_edit else ''}>
          </div>
          <div class="col-12 col-lg-3">
            <label class="form-label">狼人单局上限</label>
            <input class="form-control" type="number" step="0.01" min="0" name="werewolves_point_cap" value="{escape(_format_setting_number(settings.get('camp_expected_point_caps', {}).get('werewolves')))}" {'readonly' if not can_edit else ''}>
          </div>
          <div class="col-12 col-lg-3">
            <label class="form-label">7-12 名额</label>
            <input class="form-control" type="number" step="1" min="0" max="12" name="middle_slots" value="{escape(str(int(day.get('middle_slots') or 0)))}" {'readonly' if not can_edit else ''}>
          </div>
        </div>
        <div class="table-responsive mt-3">
          <table class="table align-middle">
            <thead><tr><th>阵营</th><th>胜率先验 (%)</th><th>胜率下限 (%)</th><th>基础分下限</th></tr></thead>
            <tbody>{''.join(camp_rows)}</tbody>
          </table>
        </div>
        <div class="row g-3 mt-1">
          <div class="col-6 col-lg-2"><label class="form-label">12+ 触发线</label><input class="form-control" type="number" step="0.01" name="elite_threshold" value="{escape(_format_setting_number(day.get('elite_threshold')))}" {'readonly' if not can_edit else ''}></div>
          <div class="col-6 col-lg-2"><label class="form-label">12+ 最低</label><input class="form-control" type="number" step="0.01" name="elite_min" value="{escape(_format_setting_number(day.get('elite_min')))}" {'readonly' if not can_edit else ''}></div>
          <div class="col-6 col-lg-2"><label class="form-label">12+ 上限</label><input class="form-control" type="number" step="0.01" name="elite_max" value="{escape(_format_setting_number(day.get('elite_max')))}" {'readonly' if not can_edit else ''}></div>
          <div class="col-6 col-lg-2"><label class="form-label">高分锚点</label><input class="form-control" type="number" step="0.01" name="elite_anchor" value="{escape(_format_setting_number(day.get('elite_anchor')))}" {'readonly' if not can_edit else ''}></div>
          <div class="col-6 col-lg-2"><label class="form-label">高分压缩</label><input class="form-control" type="number" step="0.01" name="elite_slope" value="{escape(_format_setting_number(day.get('elite_slope')))}" {'readonly' if not can_edit else ''}></div>
          <div class="col-6 col-lg-2"><label class="form-label">7-12 上限序列</label><input class="form-control" name="middle_caps" value="{escape(middle_caps_text)}" {'readonly' if not can_edit else ''}></div>
          <div class="col-6 col-lg-2"><label class="form-label">7-12 最低</label><input class="form-control" type="number" step="0.01" name="middle_min" value="{escape(_format_setting_number(day.get('middle_min')))}" {'readonly' if not can_edit else ''}></div>
          <div class="col-6 col-lg-2"><label class="form-label">7-12 压缩</label><input class="form-control" type="number" step="0.01" name="middle_slope" value="{escape(_format_setting_number(day.get('middle_slope')))}" {'readonly' if not can_edit else ''}></div>
          <div class="col-6 col-lg-2"><label class="form-label">主体区最低</label><input class="form-control" type="number" step="0.01" name="main_min" value="{escape(_format_setting_number(day.get('main_min')))}" {'readonly' if not can_edit else ''}></div>
          <div class="col-6 col-lg-2"><label class="form-label">主体区上限</label><input class="form-control" type="number" step="0.01" name="main_max" value="{escape(_format_setting_number(day.get('main_max')))}" {'readonly' if not can_edit else ''}></div>
          <div class="col-6 col-lg-2"><label class="form-label">主体区斜率</label><input class="form-control" type="number" step="0.01" name="main_slope" value="{escape(_format_setting_number(day.get('main_slope')))}" {'readonly' if not can_edit else ''}></div>
        </div>
        <div class="d-flex flex-wrap gap-2 mt-4">
          <button class="btn btn-dark" type="submit" {'disabled' if not can_edit else ''}>保存模型参数</button>
          <span class="small text-secondary align-self-center">{'只有管理员可以修改全局模型。' if not can_edit else '保存后小程序预测榜立即生效。'}</span>
        </div>
      </form>
    </section>
    """


def render_prediction_table_html(
    predictions: list[dict[str, Any]],
    *,
    table_class: str = "table align-middle",
    dark_links: bool = True,
) -> str:
    system_headers = "".join(f"<th>系统 {escape(label)}</th>" for _, label, _, _ in PREDICTION_BUCKETS)
    manual_headers = "".join(f"<th>人工 {escape(label)}</th>" for _, label, _, _ in PREDICTION_BUCKETS)
    rows = []
    for item in predictions:
        system_by_key = {entry["key"]: entry for entry in item.get("probabilities", [])}
        manual_by_key = {entry["key"]: entry for entry in item.get("manual_probabilities", [])}
        link_class = "link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" if dark_links else ""
        player_html = (
            f'<a class="{link_class}" href="{escape(item.get("player_href") or "#")}">{escape(item.get("player_name") or "")}</a>'
            if item.get("player_href")
            else escape(item.get("player_name") or "")
        )
        system_cells = "".join(
            f"<td>{escape(system_by_key.get(key, {}).get('display', '0.0%'))}</td>"
            for key, _, _, _ in PREDICTION_BUCKETS
        )
        manual_cells = "".join(
            f"<td>{escape(manual_by_key.get(key, {}).get('display', '未填写'))}</td>"
            for key, _, _, _ in PREDICTION_BUCKETS
        )
        rows.append(
            f"""
            <tr>
              <td>{escape(str(item.get('seat') or ''))}</td>
              <td>{player_html}</td>
              <td>{escape(item.get('team_name') or '')}</td>
              <td>{escape(item.get('expected_points') or '')}</td>
              <td>{escape(item.get('win_rate') or '')}</td>
              {system_cells}
              {manual_cells}
              <td>{escape(item.get('confidence') or '')}</td>
              <td>本赛季 {int(item.get('current_samples') or 0)} 场 · 其他赛季 {int(item.get('reference_samples') or 0)} 场 · 维度 {int(item.get('dimension_games') or 0)} 局</td>
            </tr>
            """
        )
    return f"""
    <div class="table-responsive">
      <table class="{escape(table_class)}">
        <thead>
          <tr><th>座位</th><th>队员</th><th>战队</th><th>预测均分</th><th>本季胜率</th>{system_headers}{manual_headers}<th>置信度</th><th>依据</th></tr>
        </thead>
        <tbody>{''.join(rows) or '<tr><td colspan="20" class="text-secondary">请先录入本场参赛选手名单。</td></tr>'}</tbody>
      </table>
    </div>
    """


def _build_match_legacy_href(ctx: RequestContext, match: dict[str, Any]) -> str:
    params: dict[str, str] = {}
    next_path = form_value(ctx.query, "next").strip()
    region = form_value(ctx.query, "region").strip()
    series = form_value(ctx.query, "series").strip()
    alert = form_value(ctx.query, "alert").strip()
    if next_path:
        params["next"] = next_path
    if region:
        params["region"] = region
    if series:
        params["series"] = series
    if alert:
        params["alert"] = alert
    if not params:
        return f"/matches/{match['match_id']}/legacy"
    return f"/matches/{match['match_id']}/legacy?{legacy.urlencode(params)}"


def _build_match_page_parts(ctx: RequestContext, match_id: str) -> tuple[str, str]:
    data = load_validated_data()
    match = get_match_by_id(data["matches"], match_id)
    if not match:
        return "未找到比赛", '<div class="alert alert-danger">没有找到对应的比赛。</div>'

    team_lookup = {team["team_id"]: team for team in data["teams"]}
    player_lookup = {player["player_id"]: player for player in data["players"]}
    competition_name = get_match_competition_name(match)
    season_name = str(match.get("season") or "").strip()
    selected_region = form_value(ctx.query, "region").strip() or None
    selected_series_slug = form_value(ctx.query, "series").strip() or None
    next_path = form_value(ctx.query, "next").strip() or build_match_next_path(match)
    score_model = normalize_match_score_model(match.get("score_model"))
    score_model_label = get_match_score_model_label(score_model)
    show_score_breakdown = uses_structured_score_model(score_model)
    match_scoring_rule = match.get("scoring_rule") or resolve_scoring_rule_for_scope(
        data, competition_name, season_name
    )
    scoring_rule_version = int(match_scoring_rule.get("version") or 1)
    score_component_fields = (
        scoring_rule_component_fields(match_scoring_rule)
        or MATCH_SCORE_COMPONENT_FIELDS
    ) if show_score_breakdown else []
    participant_by_id = {
        str(participant.get("player_id") or "").strip(): participant
        for participant in match["players"]
        if str(participant.get("player_id") or "").strip()
    }
    legacy_href = _build_match_legacy_href(ctx, match)

    def render_award_player(player_id: str, empty_label: str) -> str:
        if not player_id:
            return f'<div class="small text-secondary">{escape(empty_label)}</div>'
        participant = participant_by_id.get(player_id)
        player = player_lookup.get(player_id)
        display_name = player["display_name"] if player else player_id
        meta_parts = []
        if participant:
            seat = participant.get("seat")
            role = str(participant.get("role") or "").strip()
            team_name = team_lookup.get(participant.get("team_id"), {}).get(
                "name",
                str(participant.get("team_id") or "").strip(),
            )
            if seat:
                meta_parts.append(f"{seat}号")
            if role:
                meta_parts.append(role)
            if team_name:
                meta_parts.append(team_name)
        meta_html = ""
        if meta_parts:
            meta_html = f'<div class="small-muted mt-2">{" · ".join(escape(part) for part in meta_parts)}</div>'
        if not player:
            return f'<span class="fw-semibold fs-4">{escape(display_name)}</span>{meta_html}'
        detail_path = build_scoped_path(
            f"/players/{player_id}",
            competition_name,
            season_name,
            selected_region,
            selected_series_slug,
        )
        return (
            f'<a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover '
            f'fw-semibold fs-4" href="{escape(detail_path)}">{escape(display_name)}</a>'
            f"{meta_html}"
        )

    team_scores: dict[str, float] = {}
    for participant in match["players"]:
        if not participant.get("team_id"):
            continue
        team_scores.setdefault(participant["team_id"], 0.0)
        team_scores[participant["team_id"]] += float(participant["points_earned"])

    score_rows = [
        (
            team_id,
            team_lookup.get(team_id, {}).get("name", team_id),
            round(score, 2),
        )
        for team_id, score in sorted(
            team_scores.items(),
            key=lambda item: (-item[1], team_lookup.get(item[0], {}).get("name", item[0])),
        )
    ]
    scoreboard_html = "".join(
        f"""
        <div class="col-12 col-md-6">
          <div class="stat-card h-100 p-4 shadow-sm border-0">
            <div class="stat-label">战队积分</div>
            <div class="stat-value mt-2">{score:.2f}</div>
            <div class="small-muted mt-2">{escape(team_name)}</div>
          </div>
        </div>
        """
        for _, team_name, score in score_rows
    )
    winning_camp = str(match.get("winning_camp") or "").strip()
    awards_html = f"""
        <div class="col-12 col-md-4">
          <div class="stat-card h-100 p-4 shadow-sm border-0">
            <div class="stat-label">MVP</div>
            <div class="mt-2">{render_award_player(str(match.get('mvp_player_id') or '').strip(), '暂未设置 MVP')}</div>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="stat-card h-100 p-4 shadow-sm border-0">
            <div class="stat-label">SVP</div>
            <div class="mt-2">{render_award_player(str(match.get('svp_player_id') or '').strip(), '暂未设置 SVP')}</div>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="stat-card h-100 p-4 shadow-sm border-0">
            <div class="stat-label">背锅</div>
            <div class="mt-2">{
                '<div class="small text-secondary">好人胜利局不设背锅。</div>'
                if winning_camp == 'villagers'
                else render_award_player(str(match.get('scapegoat_player_id') or '').strip(), '暂未设置背锅选手')
            }</div>
          </div>
        </div>
    """

    participant_rows = []
    for participant in sorted(match["players"], key=lambda item: item["seat"]):
        player = player_lookup.get(participant["player_id"])
        team = team_lookup.get(participant["team_id"])
        player_name = player["display_name"] if player else participant["player_id"]
        team_name = team["name"] if team else (participant["team_id"] or "个人赛")
        stance_result = normalize_stance_result(participant)
        score_breakdown = normalize_score_breakdown(participant)
        breakdown_cells = ""
        if show_score_breakdown:
            breakdown_cells = "".join(
                f"<td>{score_breakdown[field_name]:.2f}</td>"
                for field_name, _ in score_component_fields
            )
        participant_rows.append(
            f"""
            <tr>
              <td>{participant['seat']}</td>
              <td>{
                f'<a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(build_scoped_path("/players/" + participant["player_id"], competition_name, season_name))}">{escape(player_name)}</a>'
                if player
                else f'<span class="fw-semibold">{escape(player_name)}</span>'
              }</td>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(build_scoped_path('/teams/' + participant['team_id'], competition_name, season_name))}">{escape(team_name)}</a></td>
              <td>{escape(participant['role'])}</td>
              <td>{escape(to_chinese_camp(participant['camp']))}</td>
              <td>{escape(RESULT_OPTIONS.get(participant['result'], participant['result']))}</td>
              {breakdown_cells}
              <td>{escape(STANCE_OPTIONS.get(stance_result, stance_result))}</td>
              <td>{float(participant['points_earned']):.2f}</td>
              <td>{escape(participant['notes'] or '无')}</td>
            </tr>
            """
        )

    breakdown_header_html = ""
    if show_score_breakdown:
        breakdown_header_html = "".join(
            f"<th>{escape(field_label)}</th>"
            for _, field_label in score_component_fields
        )
    predictions = build_match_score_predictions(
        data,
        match,
        competition_name,
        season_name,
        selected_region,
        selected_series_slug,
    )
    prediction_panel = f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">胜率预测</h2>
          <p class="section-copy mb-0">预测已拆分到独立页面展示，前台会并排显示系统计算概率和后台人工概率。</p>
        </div>
        <div class="d-flex flex-wrap gap-2">
          <a class="btn btn-dark" href="/matches/{escape(match_id)}/predictions?next={quote(build_scoped_path('/matches/' + match_id, competition_name, season_name))}">打开预测页</a>
          <a class="btn btn-outline-dark" href="/prediction-admin?match_id={escape(match_id)}">后台人工概率</a>
        </div>
      </div>
      <div class="alert alert-warning fw-semibold mb-0">当前本场已有 {len(predictions)} 名选手可预测。预测仅用于赛前参考；未录入结果的比赛不会计入历史样本。</div>
    </section>
    """

    edit_button = ""
    if can_manage_matches(ctx.current_user, data, competition_name):
        edit_button = (
            f'<a class="btn btn-dark" href="/matches/{escape(match_id)}/edit?next='
            f'{quote(build_scoped_path("/matches/" + match_id, competition_name, season_name))}">编辑比赛</a>'
        )

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">比赛详情页</div>
          <h1 class="hero-title mb-3">{escape(competition_name)} · {escape(season_name)}</h1>
          <p class="hero-copy mb-0">这里展示单场比赛的完整信息，包括比赛编号、阶段、参赛分组以及所有上场成员的个人明细。</p>
          <div class="d-flex flex-wrap gap-2 mt-4">
            <span class="chip">编号 {escape(match['match_id'])}</span>
            <span class="chip">{escape(resolve_stage_label_for_scope(data, competition_name, season_name, match['stage']))}</span>
            <span class="chip">第 {match['round']} 轮</span>
            <span class="chip">计分模型 {escape(score_model_label)} · V{scoring_rule_version}</span>
            <a class="switcher-chip" href="{escape(build_match_day_path(match['played_on'], build_scoped_path('/matches/' + match_id, competition_name, season_name)))}">{escape(match['played_on'])}</a>
          </div>
          <div class="d-flex flex-wrap gap-2 mt-3">
            <a class="btn btn-outline-dark" href="{escape(next_path)}">返回上一页</a>
            {edit_button}
            <a class="btn btn-outline-dark" href="{escape(legacy_href)}">旧版比赛页</a>
          </div>
        </div>
        <div class="hero-stage-card">
          <div class="official-mark">Match Detail</div>
          <div class="hero-stage-label">Match Overview</div>
          <div class="hero-stage-title">{escape(match['match_id'])}</div>
          <div class="hero-stage-note">比赛详情页会固定当前系列赛和赛季口径，方便从战队页、队员页和赛事页继续回看单场内容。</div>
          <div class="hero-stage-grid">
            <div class="hero-stage-metric">
              <span>房间</span>
              <strong>{escape(match['table_label'])}</strong>
              <small>{escape(match['format'])}</small>
            </div>
            <div class="hero-stage-metric">
              <span>时长</span>
              <strong>{match['duration_minutes']} 分钟</strong>
              <small>完整比赛耗时</small>
            </div>
            <div class="hero-stage-metric">
              <span>胜利阵营</span>
              <strong>{escape(to_chinese_camp(match['winning_camp']))}</strong>
              <small>本局最终结果</small>
            </div>
            <div class="hero-stage-metric">
              <span>参赛分组</span>
              <strong>{escape(str(match.get('group_label') or '未设置'))}</strong>
              <small>本场所属分组</small>
            </div>
          </div>
        </div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">本局奖项</h2>
          <p class="section-copy mb-0">这里记录每场比赛的 MVP、SVP 和背锅选手；好人胜利局不会设置背锅。</p>
        </div>
      </div>
      <div class="row g-3">{awards_html}</div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">战队比分</h2>
          <p class="section-copy mb-0">按本场所有上场成员的得分累计展示，方便快速查看单场战队表现。</p>
        </div>
      </div>
      <div class="row g-3">{scoreboard_html}</div>
    </section>
    {prediction_panel}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">上场成员明细</h2>
          <p class="section-copy mb-0">点击队员或战队名称，可以继续跳转到对应的详情页，并保持当前系列赛与赛季口径。{escape('当前使用京城日报积分模型，已展开分项积分。' if show_score_breakdown else '')}</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>座位</th>
              <th>队员</th>
              <th>战队</th>
              <th>角色</th>
              <th>阵营</th>
              <th>结果</th>
              {breakdown_header_html}
              <th>站边</th>
              <th>得分</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            {''.join(participant_rows)}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <h2 class="section-title mb-2">比赛备注</h2>
      <p class="section-copy mb-0">{escape(match['notes'] or '暂无备注。')}</p>
    </section>
    """
    return f"{match['match_id']} 详情", body


def build_match_frontend_page(ctx: RequestContext, match_id: str) -> str:
    data = load_validated_data()
    match = get_match_by_id(data["matches"], match_id)
    if not match:
        return layout("未找到比赛", '<div class="alert alert-danger">没有找到对应的比赛。</div>', ctx)

    bootstrap = json.dumps(
        {
            "apiEndpoint": f"/api/matches/{match_id}",
            "alert": form_value(ctx.query, "alert").strip(),
            "legacyHref": _build_match_legacy_href(ctx, match),
        },
        ensure_ascii=False,
    )

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#122238">
    <title>{escape(str(match.get('match_id') or match_id))} 详情</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;800;900&family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/competitions-app.css">
  </head>
  <body class="competitions-app-shell match-detail-app-shell">
    <div class="shell-backdrop"></div>
    <header class="shell-header">
      <div class="shell-brand">
        <a class="shell-brand-link" href="/dashboard" aria-label="返回赛事首页">
          <span class="shell-brand-mark" aria-hidden="true"></span>
          <span>WOLF</span>
        </a>
        <span class="shell-brand-copy">比赛详情 · API Driven</span>
      </div>
      <nav class="shell-nav" aria-label="主导航">
        <a class="shell-nav-link" href="/dashboard">仪表盘</a>
        <a class="shell-nav-link is-active" href="/competitions">比赛中心</a>
        <a class="shell-nav-link" href="/teams">战队</a>
        <a class="shell-nav-link" href="/players">选手</a>
        <a class="shell-nav-link" href="/guilds">门派</a>
        <a class="shell-nav-link" href="/schedule">赛程日历</a>
      </nav>
      {_build_match_account_html(ctx)}
    </header>
    <main id="match-app" class="competitions-layout match-detail-layout" aria-live="polite">
      <section class="competitions-panel competitions-loading-shell">
        <div class="competitions-section-kicker">Loading Match</div>
        <h1 class="competitions-title">正在加载比赛详情</h1>
        <p class="competitions-copy">新前端会通过独立 API 拉取比赛概览、奖项、战队比分和上场成员。</p>
      </section>
    </main>
    <script>window.__WEREWOLF_MATCH_BOOTSTRAP__ = {bootstrap};</script>
    <script src="/assets/match-app.js" defer></script>
  </body>
</html>
"""


def _build_match_prediction_context(ctx: RequestContext, match_id: str) -> tuple[dict[str, Any] | None, str]:
    data = load_validated_data()
    match = get_match_by_id(data["matches"], match_id)
    if not match:
        return None, "没有找到对应的比赛。"
    competition_name = get_match_competition_name(match)
    season_name = str(match.get("season") or "").strip()
    selected_region = form_value(ctx.query, "region").strip() or None
    selected_series_slug = form_value(ctx.query, "series").strip() or None
    predictions = build_match_score_predictions(
        data,
        match,
        competition_name,
        season_name,
        selected_region,
        selected_series_slug,
    )
    return {
        "data": data,
        "match": match,
        "competition_name": competition_name,
        "season_name": season_name,
        "selected_region": selected_region,
        "selected_series_slug": selected_series_slug,
        "predictions": predictions,
    }, ""


def get_match_prediction_page(ctx: RequestContext, match_id: str, alert: str = "") -> str:
    context, error = _build_match_prediction_context(ctx, match_id)
    if not context:
        return layout("胜率预测", f'<div class="alert alert-danger">{escape(error)}</div>', ctx)
    match = context["match"]
    competition_name = context["competition_name"]
    season_name = context["season_name"]
    next_path = form_value(ctx.query, "next").strip() or build_scoped_path("/matches/" + match_id, competition_name, season_name)
    table_html = render_prediction_table_html(context["predictions"])
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">Score Forecast</div>
          <h1 class="hero-title mb-3">胜率预测</h1>
          <p class="hero-copy mb-0">系统计算概率和后台人工概率并排展示，适合在赛前录入参赛名单后做分数区间判断。</p>
          <div class="d-flex flex-wrap gap-2 mt-4">
            <span class="chip">{escape(competition_name)}</span>
            <span class="chip">{escape(season_name)}</span>
            <span class="chip">比赛 {escape(match_id)}</span>
            <span class="chip">{escape(resolve_stage_label_for_scope(context['data'], competition_name, season_name, match.get('stage')))}</span>
          </div>
          <div class="d-flex flex-wrap gap-2 mt-3">
            <a class="btn btn-outline-dark" href="{escape(next_path)}">返回比赛详情</a>
            <a class="btn btn-outline-dark" href="/predictions?competition={quote(competition_name)}&season={quote(season_name)}&played_on={quote(str(match.get('played_on') or ''))}">查看当天三局预测</a>
            <a class="btn btn-dark" href="/prediction-admin?match_id={escape(match_id)}">后台填写人工概率</a>
          </div>
        </div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">系统概率 / 人工概率</h2>
          <p class="section-copy mb-0">系统概率基于本赛季胜率、历史单局得分、个人维度数据，并参考其他赛季数据；人工概率由后台单独录入。</p>
        </div>
      </div>
      <div class="alert alert-warning fw-semibold mb-3">预测仅用于赛前参考；未录入结果的比赛不会计入历史样本。</div>
      {table_html}
    </section>
    """
    return layout("胜率预测", body, ctx, alert=alert or form_value(ctx.query, "alert").strip())


def _prediction_day_scope(
    ctx: RequestContext,
    data: dict[str, Any],
) -> tuple[list[str], str, list[str], str, str]:
    series_catalog = legacy.load_series_catalog(data)
    jcds_competitions = sorted(
        {
            str(entry.get("competition_name") or "").strip()
            for entry in series_catalog
            if str(entry.get("series_slug") or "").strip() == "jcds"
        }
    )
    selected_competition = form_value(ctx.query, "scenario_competition").strip()
    if selected_competition not in jcds_competitions:
        selected_competition = jcds_competitions[0] if jcds_competitions else ""
    season_names = (
        legacy.list_seasons(
            data,
            selected_competition,
            include_non_ongoing=True,
            selected_season=form_value(ctx.query, "scenario_season").strip() or None,
        )
        if selected_competition
        else []
    )
    selected_season = form_value(ctx.query, "scenario_season").strip()
    if selected_season not in season_names:
        selected_season = season_names[0] if season_names else ""
    played_on = form_value(ctx.query, "scenario_date").strip() or legacy.china_today_label()
    try:
        date.fromisoformat(played_on)
    except ValueError:
        played_on = legacy.china_today_label()
    return jcds_competitions, selected_competition, season_names, selected_season, played_on


def _prediction_day_scenario_admin_html(
    ctx: RequestContext,
    data: dict[str, Any],
) -> str:
    if not is_admin_user(ctx.current_user):
        return ""
    (
        competitions,
        selected_competition,
        season_names,
        selected_season,
        played_on,
    ) = _prediction_day_scope(ctx, data)
    if not competitions:
        return '<div class="alert alert-secondary">当前没有 series_slug=jcds 的赛事，无法发布三局预测。</div>'
    scenarios = load_prediction_day_scenarios()
    scenario = scenarios.get(
        prediction_day_scenario_key(selected_competition, selected_season, played_on)
    )
    roster = list((scenario or {}).get("roster") or [])[:12]
    roster.extend({} for _ in range(12 - len(roster)))
    team_lookup = {
        str(team.get("team_id") or ""): team for team in data.get("teams", [])
    }
    player_options = []
    player_team_map: dict[str, str] = {}
    for player in sorted(
        data.get("players", []),
        key=lambda item: str(item.get("display_name") or item.get("player_id") or ""),
    ):
        player_name = str(player.get("display_name") or player.get("player_id") or "").strip()
        if not player_name:
            continue
        team = team_lookup.get(str(player.get("team_id") or ""), {})
        team_name = str(team.get("name") or "").strip()
        player_team_map[player_name] = team_name
        player_options.append(f'<option value="{escape(player_name)}"></option>')
    team_options = "".join(
        f'<option value="{escape(str(team.get("name") or team.get("team_id") or ""))}"></option>'
        for team in sorted(
            data.get("teams", []),
            key=lambda item: str(item.get("name") or item.get("team_id") or ""),
        )
    )
    competition_options = "".join(
        f'<option value="{escape(item)}"{" selected" if item == selected_competition else ""}>{escape(item)}</option>'
        for item in competitions
    )
    season_options = "".join(
        f'<option value="{escape(item)}"{" selected" if item == selected_season else ""}>{escape(item)}</option>'
        for item in season_names
    )
    rows = []
    for index, row in enumerate(roster, start=1):
        override = row.get("manual_total_override")
        override_value = "" if override in (None, "") else _format_setting_number(override)
        rows.append(
            f"""
            <tr>
              <td>{index}</td>
              <td><input class="form-control scenario-player-input" list="prediction-player-options" name="scenario_player_{index}" data-row="{index}" value="{escape(str(row.get('player_name') or ''))}" autocomplete="off" required></td>
              <td><input class="form-control" list="prediction-team-options" name="scenario_team_{index}" id="scenario-team-{index}" value="{escape(str(row.get('team_name') or ''))}" autocomplete="off" required></td>
              <td><input class="form-control" type="number" min="-10" max="30" step="0.5" name="scenario_override_{index}" value="{escape(override_value)}" placeholder="自动"></td>
            </tr>
            """
        )
    map_json = json.dumps(player_team_map, ensure_ascii=False).replace("</", "<\\/")
    status_copy = (
        f"已发布 · {escape(str((scenario or {}).get('updated_at') or ''))} · 操作者 {escape(str((scenario or {}).get('updated_by') or ''))}"
        if scenario and scenario.get("published")
        else "未发布"
    )
    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <div class="eyebrow mb-2">Three-game Scenario</div>
          <h2 class="section-title mb-2">比赛日三局预测</h2>
          <p class="section-copy mb-0">固定录入12人一次，发布后系统以每局4神、4民、4狼随机模拟三局；陌生名称不会创建正式档案。</p>
        </div>
        <span class="chip">{status_copy}</span>
      </div>
      <form method="get" action="/prediction-admin" class="row g-3 align-items-end mb-4">
        <div class="col-12 col-lg-4"><label class="form-label">赛事</label><select class="form-select" name="scenario_competition">{competition_options}</select></div>
        <div class="col-12 col-lg-3"><label class="form-label">赛季</label><select class="form-select" name="scenario_season">{season_options}</select></div>
        <div class="col-12 col-lg-3"><label class="form-label">比赛日</label><input class="form-control" type="date" name="scenario_date" value="{escape(played_on)}"></div>
        <div class="col-12 col-lg-2"><button class="btn btn-outline-dark w-100" type="submit">切换日期</button></div>
      </form>
      <form method="post" action="/prediction-admin?scenario_competition={quote(selected_competition)}&scenario_season={quote(selected_season)}&scenario_date={quote(played_on)}">
        <input type="hidden" name="scenario_competition" value="{escape(selected_competition)}">
        <input type="hidden" name="scenario_season" value="{escape(selected_season)}">
        <input type="hidden" name="scenario_date" value="{escape(played_on)}">
        <datalist id="prediction-player-options">{''.join(player_options)}</datalist>
        <datalist id="prediction-team-options">{team_options}</datalist>
        <div class="table-responsive">
          <table class="table align-middle">
            <thead><tr><th>序号</th><th>选手</th><th>战队</th><th>日总分修正</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
        <div class="d-flex flex-wrap gap-2 mt-3">
          <button class="btn btn-dark" type="submit" name="action" value="save_day_scenario">保存并发布</button>
          <button class="btn btn-outline-dark" type="submit" name="action" value="resimulate_day_scenario">重新模拟</button>
          <button class="btn btn-outline-danger" type="submit" name="action" value="unpublish_day_scenario" formnovalidate {'disabled' if not scenario or not scenario.get('published') else ''}>取消发布</button>
          <a class="btn btn-outline-dark" href="/predictions?competition={quote(selected_competition)}&season={quote(selected_season)}&played_on={quote(played_on)}">查看公开页</a>
        </div>
      </form>
      <script>
        (() => {{
          const teamByPlayer = {map_json};
          document.querySelectorAll('.scenario-player-input').forEach((input) => {{
            input.addEventListener('change', () => {{
              const teamInput = document.getElementById(`scenario-team-${{input.dataset.row}}`);
              if (teamInput && teamByPlayer[input.value]) teamInput.value = teamByPlayer[input.value];
            }});
          }});
        }})();
      </script>
    </section>
    """


def get_prediction_admin_page(ctx: RequestContext, alert: str = "") -> str:
    if not ctx.current_user:
        return layout("胜率预测后台", '<div class="alert alert-danger">请先登录。</div>', ctx)
    data = load_validated_data()
    scenario_editor = _prediction_day_scenario_admin_html(ctx, data)
    match_id = form_value(ctx.query, "match_id").strip()
    matches = sorted(
        data.get("matches", []),
        key=lambda item: (
            str(item.get("played_on") or ""),
            int(item.get("round") or 0),
            int(item.get("game_no") or 0),
            str(item.get("match_id") or ""),
        ),
        reverse=True,
    )
    selected_match = get_match_by_id(matches, match_id) if match_id else (matches[0] if matches else None)
    if not selected_match:
        return layout("胜率预测后台", '<div class="alert alert-secondary">当前还没有比赛可以维护预测。</div>', ctx)
    selected_match_id = str(selected_match.get("match_id") or "")
    competition_name = get_match_competition_name(selected_match)
    if not can_manage_matches(ctx.current_user, data, competition_name):
        return layout("胜率预测后台", '<div class="alert alert-danger">你没有权限维护这场比赛的预测。</div>', ctx)
    model_settings = legacy.load_prediction_model_settings()
    model_settings_form = _prediction_model_settings_form_html(model_settings, is_admin_user(ctx.current_user))
    season_name = str(selected_match.get("season") or "").strip()
    context, error = _build_match_prediction_context(ctx, selected_match_id)
    if not context:
        return layout("胜率预测后台", f'<div class="alert alert-danger">{escape(error)}</div>', ctx)
    predictions = context["predictions"]
    match_options = "".join(
        f'<option value="{escape(str(item.get("match_id") or ""))}"{" selected" if str(item.get("match_id") or "") == selected_match_id else ""}>{escape(str(item.get("played_on") or ""))} · {escape(get_match_competition_name(item))} · {escape(str(item.get("season") or ""))} · {escape(str(item.get("match_id") or ""))}</option>'
        for item in matches[:300]
    )
    headers = "".join(f"<th>{escape(label)} (%)</th>" for _, label, _, _ in PREDICTION_BUCKETS)
    rows = []
    for item in predictions:
        manual_by_key = {entry["key"]: entry for entry in item.get("manual_probabilities", [])}
        inputs = "".join(
            f'<td><input class="form-control form-control-sm" type="number" min="0" max="100" step="0.1" name="{escape(item["player_id"])}__{escape(key)}" value="{escape(_format_manual_input_value(manual_by_key.get(key, {}).get("value")))}"></td>'
            for key, _, _, _ in PREDICTION_BUCKETS
        )
        rows.append(
            f"""
            <tr>
              <td>{escape(str(item.get('seat') or ''))}</td>
              <td>{escape(item.get('player_name') or '')}</td>
              <td>{escape(item.get('team_name') or '')}</td>
              <td>{escape(item.get('expected_points') or '')}</td>
              {inputs}
            </tr>
            """
        )
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">Prediction Admin</div>
      <h1 class="display-6 fw-semibold mb-3">胜率预测后台</h1>
      <p class="mb-0 opacity-75">这里维护预测模型参数和单场人工概率。模型参数保存后，小程序比赛日预测榜会立即按新口径展示。</p>
    </section>
    {model_settings_form}
    {scenario_editor}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <form method="get" action="/prediction-admin" class="row g-3 align-items-end">
        <div class="col-12 col-lg-8">
          <label class="form-label">选择比赛</label>
          <select class="form-select" name="match_id">{match_options}</select>
        </div>
        <div class="col-12 col-lg-4">
          <button class="btn btn-dark w-100" type="submit">切换比赛</button>
        </div>
      </form>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">{escape(selected_match_id)} 人工概率</h2>
          <p class="section-copy mb-0">{escape(competition_name)} · {escape(season_name)}。请填写 0-100 的百分比，留空表示前台显示“未填写”。</p>
        </div>
        <a class="btn btn-outline-dark" href="/matches/{escape(selected_match_id)}/predictions">查看前台预测页</a>
      </div>
      <form method="post" action="/prediction-admin?match_id={escape(selected_match_id)}">
        <input type="hidden" name="match_id" value="{escape(selected_match_id)}">
        <div class="table-responsive">
          <table class="table align-middle">
            <thead><tr><th>座位</th><th>队员</th><th>战队</th><th>系统预测均分</th>{headers}</tr></thead>
            <tbody>{''.join(rows) or '<tr><td colspan="10" class="text-secondary">请先录入这场比赛的参赛选手名单。</td></tr>'}</tbody>
          </table>
        </div>
        <div class="d-flex flex-wrap gap-2 mt-3">
          <button class="btn btn-dark" type="submit">保存人工概率</button>
          <a class="btn btn-outline-dark" href="/prediction-admin?match_id={escape(selected_match_id)}">重置</a>
        </div>
      </form>
    </section>
    """
    return layout("胜率预测后台", body, ctx, alert=alert or form_value(ctx.query, "alert").strip())


def _prediction_day_redirect(
    start_response,
    competition_name: str,
    season_name: str,
    played_on: str,
    alert: str,
):
    return legacy.redirect(
        start_response,
        "/prediction-admin?"
        + urlencode(
            {
                "scenario_competition": competition_name,
                "scenario_season": season_name,
                "scenario_date": played_on,
                "alert": alert,
            }
        ),
    )


def _handle_prediction_day_scenario_admin(
    ctx: RequestContext,
    start_response,
    data: dict[str, Any],
    action: str,
):
    if not is_admin_user(ctx.current_user):
        return legacy.start_response_html(
            start_response,
            "403 Forbidden",
            get_prediction_admin_page(ctx, "只有管理员可以发布比赛日三局预测。"),
        )
    competition_name = form_value(ctx.form, "scenario_competition").strip()
    season_name = form_value(ctx.form, "scenario_season").strip()
    played_on = form_value(ctx.form, "scenario_date").strip()
    jcds_competitions = {
        str(entry.get("competition_name") or "").strip()
        for entry in legacy.load_series_catalog(data)
        if str(entry.get("series_slug") or "").strip() == "jcds"
    }
    valid_seasons = legacy.list_seasons(
        data,
        competition_name,
        include_non_ongoing=True,
        selected_season=season_name or None,
    )
    try:
        date.fromisoformat(played_on)
    except ValueError:
        played_on = ""
    if competition_name not in jcds_competitions or season_name not in valid_seasons or not played_on:
        return legacy.start_response_html(
            start_response,
            "400 Bad Request",
            get_prediction_admin_page(ctx, "赛事、赛季或比赛日无效。"),
        )
    key = prediction_day_scenario_key(competition_name, season_name, played_on)
    scenarios = load_prediction_day_scenarios()
    if action == "unpublish_day_scenario":
        scenario = scenarios.get(key)
        if scenario:
            scenario["published"] = False
            scenario["updated_by"] = str(ctx.current_user.get("username") or "")
            scenario["updated_at"] = ctx.now_label
            scenarios[key] = scenario
            save_prediction_day_scenarios(scenarios)
            legacy.audit_action(
                ctx,
                "prediction_day.unpublish",
                target_type="prediction_day_scenario",
                target_id=key,
                summary=f"取消发布 {competition_name} {season_name} {played_on} 三局预测",
            )
        return _prediction_day_redirect(
            start_response, competition_name, season_name, played_on, "该比赛日预测已取消发布。"
        )

    players_by_name: dict[str, list[dict[str, Any]]] = {}
    for player in data.get("players", []):
        player_name = str(player.get("display_name") or player.get("player_id") or "").strip()
        if player_name:
            players_by_name.setdefault(player_name.casefold(), []).append(player)
    teams_by_name: dict[str, list[dict[str, Any]]] = {}
    for team in data.get("teams", []):
        team_name = str(team.get("name") or team.get("team_id") or "").strip()
        if team_name:
            teams_by_name.setdefault(team_name.casefold(), []).append(team)
    roster = []
    seen_players: set[str] = set()
    for index in range(1, 13):
        player_name = form_value(ctx.form, f"scenario_player_{index}").strip()
        team_name = form_value(ctx.form, f"scenario_team_{index}").strip()
        if not player_name or not team_name:
            return legacy.start_response_html(
                start_response,
                "400 Bad Request",
                get_prediction_admin_page(ctx, "12名选手和战队必须全部填写。"),
            )
        matched_players = players_by_name.get(player_name.casefold(), [])
        player = matched_players[0] if len(matched_players) == 1 else {}
        matched_teams = teams_by_name.get(team_name.casefold(), [])
        team = matched_teams[0] if len(matched_teams) == 1 else {}
        player_id = str(player.get("player_id") or "").strip()
        team_id = str(team.get("team_id") or "").strip()
        duplicate_key = f"id:{player_id}" if player_id else f"name:{player_name.casefold()}"
        if duplicate_key in seen_players:
            return legacy.start_response_html(
                start_response,
                "400 Bad Request",
                get_prediction_admin_page(ctx, f"选手“{player_name}”重复，12行不得重复。"),
            )
        seen_players.add(duplicate_key)
        override_text = form_value(ctx.form, f"scenario_override_{index}").strip()
        override = None
        if override_text:
            try:
                override = float(override_text)
            except ValueError:
                override = 99.0
            if not -10.0 <= override <= 30.0 or abs(override * 2.0 - round(override * 2.0)) > 0.000001:
                return legacy.start_response_html(
                    start_response,
                    "400 Bad Request",
                    get_prediction_admin_page(ctx, "日总分修正只能填写 -10～30、步长0.5的数字。"),
                )
        roster.append(
            {
                "seat": index,
                "player_id": player_id,
                "scenario_player_id": _stable_scenario_player_id(
                    competition_name, season_name, played_on, player_name, index
                ),
                "player_name": player_name,
                "team_id": team_id,
                "team_name": team_name,
                "manual_total_override": override,
            }
        )
    scenario = normalize_prediction_day_scenario(
        {
            "version": PREDICTION_DAY_SCENARIO_VERSION,
            "competition_name": competition_name,
            "season_name": season_name,
            "played_on": played_on,
            "published": True,
            "roster": roster,
            "updated_by": str(ctx.current_user.get("username") or ""),
            "updated_at": ctx.now_label,
            "published_at": ctx.now_label,
        }
    )
    scenarios[key] = scenario or {}
    save_prediction_day_scenarios(scenarios)
    legacy.audit_action(
        ctx,
        "prediction_day.publish" if action == "save_day_scenario" else "prediction_day.resimulate",
        target_type="prediction_day_scenario",
        target_id=key,
        summary=f"发布 {competition_name} {season_name} {played_on} 三局预测",
        metadata={"roster_size": len(roster), "scenario_version": PREDICTION_DAY_SCENARIO_VERSION},
    )
    alert = "比赛日三局预测已保存并发布。" if action == "save_day_scenario" else "三局预测已按固定种子重新模拟并发布。"
    return _prediction_day_redirect(start_response, competition_name, season_name, played_on, alert)


def handle_prediction_admin(ctx: RequestContext, start_response):
    if not ctx.current_user:
        return legacy.redirect(start_response, "/login?next=/prediction-admin")
    if ctx.method == "GET":
        return legacy.start_response_html(start_response, "200 OK", get_prediction_admin_page(ctx))
    action = form_value(ctx.form, "action").strip()
    if action == "save_model_settings":
        if not is_admin_user(ctx.current_user):
            return legacy.start_response_html(start_response, "403 Forbidden", get_prediction_admin_page(ctx, "只有管理员可以修改全局预测模型。"))
        current_settings = legacy.load_prediction_model_settings()
        next_settings = _prediction_settings_from_form(ctx, current_settings)
        legacy.save_prediction_model_settings(next_settings)
        return legacy.redirect(start_response, f"/prediction-admin?alert={quote('预测模型参数已保存。')}")
    data = load_validated_data()
    if action in {
        "save_day_scenario",
        "resimulate_day_scenario",
        "unpublish_day_scenario",
    }:
        return _handle_prediction_day_scenario_admin(
            ctx, start_response, data, action
        )
    match_id = form_value(ctx.form, "match_id").strip() or form_value(ctx.query, "match_id").strip()
    match = get_match_by_id(data.get("matches", []), match_id)
    if not match:
        return legacy.start_response_html(start_response, "200 OK", get_prediction_admin_page(ctx, "没有找到对应的比赛。"))
    competition_name = get_match_competition_name(match)
    if not can_manage_matches(ctx.current_user, data, competition_name):
        return legacy.start_response_html(start_response, "403 Forbidden", get_prediction_admin_page(ctx, "你没有权限维护这场比赛的预测。"))
    all_manual = load_manual_score_predictions()
    next_match_values: dict[str, dict[str, float | None]] = {}
    for participant in match.get("players", []):
        player_id = str(participant.get("player_id") or "").strip()
        if not player_id:
            continue
        values: dict[str, float | None] = {}
        for key, _, _, _ in PREDICTION_BUCKETS:
            raw_value = form_value(ctx.form, f"{player_id}__{key}").strip()
            if raw_value == "":
                values[key] = None
                continue
            try:
                values[key] = float(raw_value)
            except ValueError:
                return legacy.start_response_html(
                    start_response,
                    "200 OK",
                    get_prediction_admin_page(ctx, "人工概率只能填写 0-100 的数字。"),
                )
        normalized = normalize_manual_prediction(values)
        if any(value is not None for value in normalized.values()):
            next_match_values[player_id] = normalized
    if next_match_values:
        all_manual[match_id] = next_match_values
    else:
        all_manual.pop(match_id, None)
    save_manual_score_predictions(all_manual)
    return legacy.redirect(start_response, f"/prediction-admin?match_id={quote(match_id)}&alert={quote('人工概率已保存。')}")


def _build_match_account_html(ctx: RequestContext) -> str:
    if ctx.current_user:
        display_name = ctx.current_user.get("display_name") or ctx.current_user["username"]
        role_label = account_role_label(ctx.current_user)
        return f"""
        <div class="shell-account">
          <span class="shell-account-label">{escape(display_name)} · {escape(role_label)}</span>
          <a class="shell-button shell-button-secondary" href="/profile">控制台</a>
          <form method="post" action="/logout" class="shell-inline-form">
            <button type="submit" class="shell-button shell-button-secondary">退出</button>
          </form>
        </div>
        """
    return """
        <div class="shell-account">
          <a class="shell-button shell-button-secondary" href="/login">登录</a>
        </div>
        """


def _serialize_match_detail_payload(ctx: RequestContext, match_id: str) -> dict[str, Any]:
    data = load_validated_data()
    match = get_match_by_id(data["matches"], match_id)
    legacy_href = _build_match_legacy_href(ctx, match or {"match_id": match_id})
    if not match:
        return {
            "not_found": True,
            "error": "没有找到对应的比赛。",
            "title": "未找到比赛",
            "alert": form_value(ctx.query, "alert").strip(),
            "legacy_href": legacy_href,
        }

    team_lookup = {team["team_id"]: team for team in data["teams"]}
    player_lookup = {player["player_id"]: player for player in data["players"]}
    competition_name = get_match_competition_name(match)
    season_name = str(match.get("season") or "").strip()
    match_stage = str(match.get("stage") or "").strip()
    team_group_map = match_team_group_map(data, match)
    regular_season_group_labels = match_group_labels(data, match)
    selected_region = form_value(ctx.query, "region").strip() or None
    selected_series_slug = form_value(ctx.query, "series").strip() or None
    next_path = form_value(ctx.query, "next").strip() or build_match_next_path(match)
    score_model = normalize_match_score_model(match.get("score_model"))
    score_model_label = get_match_score_model_label(score_model)
    show_score_breakdown = uses_structured_score_model(score_model)
    match_scoring_rule = match.get("scoring_rule") or resolve_scoring_rule_for_scope(
        data, competition_name, season_name
    )
    scoring_rule_version = int(match_scoring_rule.get("version") or 1)
    score_component_fields = (
        scoring_rule_component_fields(match_scoring_rule)
        or MATCH_SCORE_COMPONENT_FIELDS
    ) if show_score_breakdown else []
    participants = []
    team_scores: dict[str, float] = {}
    participant_by_id = {}
    for participant in sorted(match.get("players", []), key=lambda item: int(item.get("seat") or 0)):
        player_id = str(participant.get("player_id") or "").strip()
        team_id = str(participant.get("team_id") or "").strip()
        player = player_lookup.get(player_id, {})
        team = team_lookup.get(team_id, {})
        has_player_profile = bool(player)
        team_scores[team_id] = team_scores.get(team_id, 0.0) + float(participant.get("points_earned") or 0)
        participant_by_id[player_id] = participant
        breakdown = normalize_score_breakdown(participant) if show_score_breakdown else {}
        participant_payload = {
                "seat": participant.get("seat") or 0,
                "player_id": player_id,
                "player_name": player.get("display_name") or player_id,
                "is_star_player": bool(player.get("is_star_player")),
                "player_href": build_scoped_path(f"/players/{player_id}", competition_name, season_name, selected_region, selected_series_slug) if has_player_profile else "",
                "team_id": team_id,
                "team_name": team.get("name") or team_id,
                "team_href": build_scoped_path(f"/teams/{team_id}", competition_name, season_name, selected_region, selected_series_slug),
                "role": participant.get("role") or "",
                "camp": to_chinese_camp(participant.get("camp") or ""),
                "result": RESULT_OPTIONS.get(participant.get("result"), participant.get("result") or ""),
                "stance": STANCE_OPTIONS.get(normalize_stance_result(participant), normalize_stance_result(participant)),
                "points": round(float(participant.get("points_earned") or 0), 2),
                "notes": participant.get("notes") or "",
                "breakdown": {label: round(float(breakdown.get(field, 0.0)), 2) for field, label in score_component_fields} if show_score_breakdown else {},
        }
        group_label = team_group_map.get(team_id, "")
        if group_label:
            badge = team_group_badge_for_stage(
                data,
                competition_name,
                season_name,
                team_id,
                match_stage,
            )
            participant_payload["group_label"] = group_label
            participant_payload["regular_season_group"] = group_label
            if badge:
                participant_payload["badges"] = [badge]
        participants.append(participant_payload)

    def award_payload(label: str, player_id: str, empty_label: str) -> dict[str, Any]:
        player_id = str(player_id or "").strip()
        participant = participant_by_id.get(player_id, {})
        player = player_lookup.get(player_id, {})
        team = team_lookup.get(str(participant.get("team_id") or ""), {})
        return {
            "label": label,
            "empty_label": empty_label,
            "player_id": player_id,
            "player_name": player.get("display_name") or (player_id if player_id else ""),
            "is_star_player": bool(player.get("is_star_player")),
            "href": build_scoped_path(f"/players/{player_id}", competition_name, season_name, selected_region, selected_series_slug) if player_id and player else "",
            "meta": " · ".join(str(part) for part in [participant.get("seat") and f"{participant.get('seat')}号", participant.get("role"), team.get("name")] if part),
        }

    winning_camp = str(match.get("winning_camp") or "").strip()
    awards = [
        award_payload("MVP", str(match.get("mvp_player_id") or ""), "暂未设置 MVP"),
        award_payload("SVP", str(match.get("svp_player_id") or ""), "暂未设置 SVP"),
        {"label": "背锅", "empty_label": "好人胜利局不设背锅。", "player_id": "", "player_name": "", "is_star_player": False, "href": "", "meta": ""}
        if winning_camp == "villagers"
        else award_payload("背锅", str(match.get("scapegoat_player_id") or ""), "暂未设置背锅选手"),
    ]
    scores = []
    for team_id, score in sorted(team_scores.items(), key=lambda item: (-item[1], team_lookup.get(item[0], {}).get("name", item[0]))):
        score_payload = {
            "team_id": team_id,
            "team_name": team_lookup.get(team_id, {}).get("name") or team_id,
            "href": build_scoped_path(f"/teams/{team_id}", competition_name, season_name, selected_region, selected_series_slug),
            "points": round(score, 2),
        }
        group_label = team_group_map.get(team_id, "")
        if group_label:
            badge = team_group_badge_for_stage(
                data,
                competition_name,
                season_name,
                team_id,
                match_stage,
            )
            score_payload["group_label"] = group_label
            score_payload["regular_season_group"] = group_label
            if badge:
                score_payload["badges"] = [badge]
        scores.append(score_payload)
    edit_href = ""
    if can_manage_matches(ctx.current_user, data, competition_name):
        edit_href = f"/matches/{quote(match_id)}/edit?next={quote(build_scoped_path('/matches/' + match_id, competition_name, season_name))}"
    predictions = build_match_score_predictions(
        data,
        match,
        competition_name,
        season_name,
        selected_region,
        selected_series_slug,
    )

    match_payload = {
        "match_id": match_id,
        "competition": competition_name,
        "season": season_name,
        "stage": resolve_stage_label_for_scope(
            data, competition_name, season_name, match.get("stage")
        ),
        "round": match.get("round") or 0,
        "game_no": match.get("game_no") or 0,
        "played_on": match.get("played_on") or "",
        "day_href": build_match_day_path(match.get("played_on") or "", build_scoped_path('/matches/' + match_id, competition_name, season_name)),
        "table_label": match.get("table_label") or "",
        "format": match.get("format") or "",
        "duration_minutes": match.get("duration_minutes") or 0,
        "winning_camp": to_chinese_camp(match.get("winning_camp") or ""),
        "group_label": match.get("group_label") or "未设置",
        "score_model": score_model_label,
        "score_rule_version": scoring_rule_version,
        "notes": match.get("notes") or "暂无备注。",
        "show_score_breakdown": show_score_breakdown,
    }
    if regular_season_group_labels:
        match_payload["group_labels"] = regular_season_group_labels

    return {
        "title": f"{match_id} 详情",
        "alert": form_value(ctx.query, "alert").strip(),
        "legacy_href": legacy_href,
        "match": match_payload,
        "actions": {
            "next_href": next_path,
            "edit_href": edit_href,
            "legacy_href": legacy_href,
            "prediction_href": f"/matches/{quote(match_id)}/predictions?next={quote(build_scoped_path('/matches/' + match_id, competition_name, season_name))}",
            "admin_href": f"/prediction-admin?match_id={quote(match_id)}" if can_manage_matches(ctx.current_user, data, competition_name) else "",
        },
        "metrics": [
            {"label": "房间", "value": match.get("table_label") or "-", "copy": match.get("format") or "未记录板型"},
            {"label": "时长", "value": f"{match.get('duration_minutes') or 0} 分钟", "copy": "完整比赛耗时"},
            {"label": "胜利阵营", "value": to_chinese_camp(match.get("winning_camp") or ""), "copy": "本局最终结果"},
            {
                "label": "参赛分组",
                "value": " / ".join(regular_season_group_labels) if regular_season_group_labels else (match.get("group_label") or "未设置"),
                "copy": "本场参赛战队分组" if regular_season_group_labels else "本场所属分组",
            },
        ],
        "awards": awards,
        "team_scores": scores,
        "score_predictions": predictions,
        "prediction_buckets": [{"key": key, "label": label} for key, label, _, _ in PREDICTION_BUCKETS],
        "participants": participants,
        "score_fields": [label for _, label in score_component_fields] if show_score_breakdown else [],
    }


def build_match_api_payload(ctx: RequestContext, match_id: str) -> dict[str, Any]:
    return _serialize_match_detail_payload(ctx, match_id)


def get_match_legacy_page(ctx: RequestContext, match_id: str) -> str:
    return legacy.get_match_page(ctx, match_id)


def handle_match_api(ctx: RequestContext, start_response, match_id: str):
    if ctx.method != "GET":
        return start_response_json(
            start_response,
            "405 Method Not Allowed",
            {"error": "match api only supports GET"},
            headers=[("Allow", "GET")],
        )
    payload = build_match_api_payload(ctx, match_id)
    status = "404 Not Found" if payload.get("not_found") else "200 OK"
    return start_response_json(start_response, status, payload)
