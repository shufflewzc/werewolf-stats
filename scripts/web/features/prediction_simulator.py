from __future__ import annotations

import bisect
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import date
from typing import Any


MODEL_VERSION = "jcds_three_game_v1"
SEED_COMPETITION = "京城大师赛广州公开赛"
SEED_SEASON = "2026广州公开赛S1"
SEED_END_DATE = "2026-05-30"
DEFAULT_WEREWOLF_WIN_RATE = 75.0 / 114.0
SIMULATION_COUNT = 10_000

MARKET_DEFINITIONS = [
    {"key": "lt_0", "label": "小0", "operator": "<", "line": 0.0},
    {"key": "lt_5", "label": "小5", "operator": "<", "line": 5.0},
    {"key": "lt_10", "label": "小10", "operator": "<", "line": 10.0},
    {"key": "gt_10", "label": "大10", "operator": ">", "line": 10.0},
    {"key": "gt_15", "label": "大15", "operator": ">", "line": 15.0},
    {"key": "gt_18", "label": "大18", "operator": ">", "line": 18.0},
]

WOLF_ROLE_NAMES = {
    "狼人",
    "狼王",
    "狼巫",
    "梦魇",
    "石像鬼",
    "血月使徒",
    "诡狼",
    "蚀日侍女",
}


def score_without_adjustment(participant: dict[str, Any]) -> float:
    return float(participant.get("points_earned") or 0.0) - float(
        participant.get("adjustment_points") or 0.0
    )


def identity_bucket(participant: dict[str, Any]) -> str:
    camp = str(participant.get("camp") or "").strip()
    role = str(participant.get("role") or "").strip()
    if camp == "werewolves" or role in WOLF_ROLE_NAMES or "狼" in role:
        return "wolf"
    if role in {"平民", "村民", "民"}:
        return "civilian"
    return "god"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _logit(value: float) -> float:
    value = _clamp(value, 0.01, 0.99)
    return math.log(value / (1.0 - value))


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def _weighted_mean(samples: list[tuple[float, float]], fallback: float = 0.0) -> float:
    total_weight = sum(weight for _, weight in samples if weight > 0)
    if total_weight <= 0:
        return fallback
    return sum(value * weight for value, weight in samples if weight > 0) / total_weight


def _posterior_rate(stats: dict[str, float], prior: float, prior_games: float) -> float:
    games = float(stats.get("games") or 0.0)
    wins = float(stats.get("wins") or 0.0)
    return (wins + prior * prior_games) / (games + prior_games)


def _posterior_mean(stats: dict[str, float], prior: float, prior_games: float) -> float:
    games = float(stats.get("games") or 0.0)
    total = float(stats.get("total") or 0.0)
    return (total + prior * prior_games) / (games + prior_games)


def _match_is_completed(match: dict[str, Any]) -> bool:
    if str(match.get("winning_camp") or "").strip() not in {"villagers", "werewolves"}:
        return False
    return bool(match.get("players"))


def _days_between(earlier: str, later: str) -> int:
    try:
        return max(0, (date.fromisoformat(later) - date.fromisoformat(earlier)).days)
    except ValueError:
        return 0


def _recency_weight(played_on: str, prediction_date: str) -> float:
    return 0.5 ** (_days_between(played_on, prediction_date) / 180.0)


def _normalize_component_weights(
    rows: list[dict[str, Any]],
    component_mass: float,
) -> list[tuple[dict[str, Any], float]]:
    if not rows or component_mass <= 0:
        return []
    total = sum(float(row.get("base_weight") or 0.0) for row in rows)
    if total <= 0:
        return []
    return [
        (row, component_mass * float(row.get("base_weight") or 0.0) / total)
        for row in rows
    ]


def build_history_model(
    data: dict[str, Any],
    *,
    competition_name: str,
    prediction_date: str,
    jcds_competitions: set[str],
) -> dict[str, Any]:
    seed_matches: list[dict[str, Any]] = []
    rolling_matches: list[dict[str, Any]] = []
    rolling_player_days: set[tuple[str, str]] = set()
    eligible_matches: list[dict[str, Any]] = []
    for match in data.get("matches", []):
        match_competition = str(match.get("competition_name") or "").strip()
        played_on = str(match.get("played_on") or "").strip()
        if match_competition not in jcds_competitions:
            continue
        if not played_on or played_on >= prediction_date or not _match_is_completed(match):
            continue
        eligible_matches.append(match)
        is_seed = (
            match_competition == SEED_COMPETITION
            and str(match.get("season") or "").strip() == SEED_SEASON
            and played_on <= SEED_END_DATE
        )
        row = {
            "match": match,
            "base_weight": (
                1.0 if match_competition == competition_name else 0.5
            )
            * _recency_weight(played_on, prediction_date),
        }
        if is_seed:
            seed_matches.append(row)
        else:
            rolling_matches.append(row)
            for participant in match.get("players", []):
                player_id = str(participant.get("player_id") or "").strip()
                if player_id and player_id.upper() != "NPC":
                    rolling_player_days.add((played_on, player_id))

    rolling_effective_samples = len(rolling_player_days)
    rolling_share = min(
        0.40,
        0.40 * rolling_effective_samples / (rolling_effective_samples + 120.0),
    )
    if not seed_matches:
        rolling_share = 1.0 if rolling_matches else 0.0
    reference_match_count = float(len(seed_matches) or len(rolling_matches) or 1)
    weighted_matches = _normalize_component_weights(
        seed_matches, reference_match_count * (1.0 - rolling_share)
    )
    weighted_matches.extend(
        _normalize_component_weights(
            rolling_matches, reference_match_count * rolling_share
        )
    )

    seed_daily_totals: dict[tuple[str, str], float] = defaultdict(float)
    seed_wolf_wins = 0
    for row in seed_matches:
        match = row["match"]
        if str(match.get("winning_camp") or "") == "werewolves":
            seed_wolf_wins += 1
        played_on = str(match.get("played_on") or "")
        for participant in match.get("players", []):
            player_id = str(participant.get("player_id") or "").strip()
            if not player_id or player_id.upper() == "NPC":
                continue
            seed_daily_totals[(played_on, player_id)] += score_without_adjustment(participant)
    seed_total_values = list(seed_daily_totals.values())

    wolf_wins = 0.0
    completed_weight = 0.0
    score_samples: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    player_win_stats: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"games": 0.0, "wins": 0.0}
    )
    team_win_stats: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"games": 0.0, "wins": 0.0}
    )
    player_score_stats: dict[tuple[str, str, str], dict[str, float]] = defaultdict(
        lambda: {"games": 0.0, "total": 0.0}
    )
    team_score_stats: dict[tuple[str, str, str], dict[str, float]] = defaultdict(
        lambda: {"games": 0.0, "total": 0.0}
    )
    population_score_stats: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"games": 0.0, "total": 0.0}
    )

    for row, match_weight in weighted_matches:
        match = row["match"]
        winning_camp = str(match.get("winning_camp") or "")
        completed_weight += match_weight
        if winning_camp == "werewolves":
            wolf_wins += match_weight
        participants = [
            participant
            for participant in match.get("players", [])
            if str(participant.get("player_id") or "").strip().upper() != "NPC"
        ]
        per_participant_weight = match_weight
        for participant in participants:
            player_id = str(participant.get("player_id") or "").strip()
            team_id = str(participant.get("team_id") or "").strip()
            bucket = identity_bucket(participant)
            camp = "werewolves" if bucket == "wolf" else "villagers"
            won = winning_camp == camp
            result_key = "win" if won else "loss"
            score = score_without_adjustment(participant)
            score_samples[(bucket, result_key)].append((score, per_participant_weight))
            population_score_stats[(bucket, result_key)]["games"] += per_participant_weight
            population_score_stats[(bucket, result_key)]["total"] += score * per_participant_weight
            if player_id:
                player_win_stats[(player_id, camp)]["games"] += per_participant_weight
                player_win_stats[(player_id, camp)]["wins"] += per_participant_weight * float(won)
                player_score_stats[(player_id, bucket, result_key)]["games"] += per_participant_weight
                player_score_stats[(player_id, bucket, result_key)]["total"] += score * per_participant_weight
            if team_id:
                team_win_stats[(team_id, camp)]["games"] += per_participant_weight
                team_win_stats[(team_id, camp)]["wins"] += per_participant_weight * float(won)
                team_score_stats[(team_id, bucket, result_key)]["games"] += per_participant_weight
                team_score_stats[(team_id, bucket, result_key)]["total"] += score * per_participant_weight

    wolf_prior = (
        wolf_wins / completed_weight if completed_weight > 0 else DEFAULT_WEREWOLF_WIN_RATE
    )
    return {
        "model_version": MODEL_VERSION,
        "wolf_prior": _clamp(wolf_prior, 0.05, 0.95),
        "score_samples": score_samples,
        "population_score_stats": population_score_stats,
        "player_win_stats": player_win_stats,
        "team_win_stats": team_win_stats,
        "player_score_stats": player_score_stats,
        "team_score_stats": team_score_stats,
        "seed_match_count": len(seed_matches),
        "rolling_match_count": len(rolling_matches),
        "rolling_sample_count": rolling_effective_samples,
        "rolling_share": rolling_share,
        "history_match_count": len(eligible_matches),
        "seed_player_day_count": len(seed_total_values),
        "seed_average_daily_total": _weighted_mean(
            [(value, 1.0) for value in seed_total_values]
        ),
        "seed_market_hit_counts": {
            definition["key"]: sum(
                value < float(definition["line"])
                if definition["operator"] == "<"
                else value > float(definition["line"])
                for value in seed_total_values
            )
            for definition in MARKET_DEFINITIONS
        },
        "seed_werewolf_wins": seed_wolf_wins,
        "seed_villager_wins": len(seed_matches) - seed_wolf_wins,
    }


class WeightedSampler:
    def __init__(self, samples: list[tuple[float, float]], fallback: float) -> None:
        cleaned = [(float(value), max(0.0, float(weight))) for value, weight in samples if weight > 0]
        if not cleaned:
            cleaned = [(fallback, 1.0)]
        self.values = [value for value, _ in cleaned]
        self.cumulative: list[float] = []
        running = 0.0
        for _, weight in cleaned:
            running += weight
            self.cumulative.append(running)
        self.total = running
        self.minimum = min(self.values)
        self.maximum = max(self.values)

    def draw(self, rng: random.Random) -> float:
        target = rng.random() * self.total
        index = bisect.bisect_left(self.cumulative, target)
        return self.values[min(index, len(self.values) - 1)]


def _participant_win_rate(
    history: dict[str, Any],
    player_id: str,
    team_id: str,
    camp: str,
) -> float:
    prior = history["wolf_prior"] if camp == "werewolves" else 1.0 - history["wolf_prior"]
    player_rate = _posterior_rate(
        history["player_win_stats"].get((player_id, camp), {"games": 0.0, "wins": 0.0}),
        prior,
        6.0,
    )
    team_rate = _posterior_rate(
        history["team_win_stats"].get((team_id, camp), {"games": 0.0, "wins": 0.0}),
        prior,
        12.0,
    )
    return _sigmoid(
        0.65 * _logit(player_rate)
        + 0.20 * _logit(team_rate)
        + 0.15 * _logit(prior)
    )


def _score_shift(
    history: dict[str, Any],
    player_id: str,
    team_id: str,
    bucket: str,
    result_key: str,
) -> float:
    population = history["population_score_stats"].get(
        (bucket, result_key), {"games": 0.0, "total": 0.0}
    )
    population_mean = _posterior_mean(population, 0.0, 0.0001)
    player_mean = _posterior_mean(
        history["player_score_stats"].get(
            (player_id, bucket, result_key), {"games": 0.0, "total": 0.0}
        ),
        population_mean,
        6.0,
    )
    team_mean = _posterior_mean(
        history["team_score_stats"].get(
            (team_id, bucket, result_key), {"games": 0.0, "total": 0.0}
        ),
        population_mean,
        12.0,
    )
    personalized_mean = 0.65 * player_mean + 0.20 * team_mean + 0.15 * population_mean
    return personalized_mean - population_mean


def _scenario_seed(
    competition_name: str,
    season_name: str,
    played_on: str,
    roster: list[dict[str, Any]],
) -> int:
    identity = {
        "competition": competition_name,
        "season": season_name,
        "played_on": played_on,
        "model_version": MODEL_VERSION,
        "roster": [
            {
                "player_id": row.get("player_id") or "",
                "player_name": row.get("player_name") or "",
                "team_id": row.get("team_id") or "",
                "team_name": row.get("team_name") or "",
            }
            for row in roster
        ],
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big")


def _round_half(value: float) -> float:
    return round(value * 2.0) / 2.0


def _market_payload(totals: list[float]) -> list[dict[str, Any]]:
    total_count = max(1, len(totals))
    payload = []
    for definition in MARKET_DEFINITIONS:
        line = float(definition["line"])
        if definition["operator"] == "<":
            hits = sum(value < line for value in totals)
        else:
            hits = sum(value > line for value in totals)
        equals = sum(value == line for value in totals)
        probability = hits / total_count
        equality_probability = equals / total_count
        payload.append(
            {
                **definition,
                "probability": round(probability, 4),
                "display": f"{probability:.1%}",
                "equality_probability": round(equality_probability, 4),
                "equality_display": f"{equality_probability:.1%}",
            }
        )
    return payload


def draw_role_assignment(rng: random.Random, player_count: int = 12) -> list[str]:
    if player_count != 12:
        raise ValueError("三局预测的每局人数必须为12。")
    indices = list(range(player_count))
    rng.shuffle(indices)
    buckets = ["" for _ in range(player_count)]
    for index in indices[:4]:
        buckets[index] = "wolf"
    for index in indices[4:8]:
        buckets[index] = "god"
    for index in indices[8:]:
        buckets[index] = "civilian"
    return buckets


def simulate_three_game_day(
    data: dict[str, Any],
    roster: list[dict[str, Any]],
    *,
    competition_name: str,
    season_name: str,
    played_on: str,
    jcds_competitions: set[str],
    simulations: int = SIMULATION_COUNT,
) -> dict[str, Any]:
    if len(roster) != 12:
        raise ValueError("三局预测必须恰好提供12名选手。")
    simulations = max(100, int(simulations))
    history = build_history_model(
        data,
        competition_name=competition_name,
        prediction_date=played_on,
        jcds_competitions=jcds_competitions,
    )
    rng = random.Random(
        _scenario_seed(competition_name, season_name, played_on, roster)
    )
    samplers: dict[tuple[str, str], WeightedSampler] = {}
    for bucket in ("god", "civilian", "wolf"):
        for result_key in ("win", "loss"):
            fallback = 5.0 if result_key == "win" else 0.0
            samplers[(bucket, result_key)] = WeightedSampler(
                history["score_samples"].get((bucket, result_key), []),
                fallback,
            )

    game_wins = [[0, 0, 0] for _ in roster]
    win_count_distribution = [[0, 0, 0, 0] for _ in roster]
    totals = [[] for _ in roster]
    bucket_counts = [defaultdict(int) for _ in roster]
    relative_strength: dict[tuple[int, str], float] = {}
    score_shifts: dict[tuple[int, str, str], float] = {}
    for index, row in enumerate(roster):
        player_id = str(row.get("player_id") or "")
        team_id = str(row.get("team_id") or "")
        for camp in ("werewolves", "villagers"):
            rate = _participant_win_rate(history, player_id, team_id, camp)
            prior = history["wolf_prior"] if camp == "werewolves" else 1.0 - history["wolf_prior"]
            relative_strength[(index, camp)] = _logit(rate) - _logit(prior)
        for bucket in ("god", "civilian", "wolf"):
            for result_key in ("win", "loss"):
                score_shifts[(index, bucket, result_key)] = _score_shift(
                    history, player_id, team_id, bucket, result_key
                )

    for _ in range(simulations):
        simulation_wins = [0 for _ in roster]
        simulation_totals = [0.0 for _ in roster]
        for game_index in range(3):
            buckets = draw_role_assignment(rng)

            wolf_relative = []
            good_relative = []
            for index, row in enumerate(roster):
                camp = "werewolves" if buckets[index] == "wolf" else "villagers"
                relative = relative_strength[(index, camp)]
                if camp == "werewolves":
                    wolf_relative.append(relative)
                else:
                    good_relative.append(relative)
            wolf_probability = _sigmoid(
                _logit(history["wolf_prior"])
                + (sum(wolf_relative) / max(1, len(wolf_relative)))
                - (sum(good_relative) / max(1, len(good_relative)))
            )
            wolf_won = rng.random() < _clamp(wolf_probability, 0.05, 0.95)

            for index, row in enumerate(roster):
                bucket = buckets[index]
                won = wolf_won if bucket == "wolf" else not wolf_won
                result_key = "win" if won else "loss"
                base_score = samplers[(bucket, result_key)].draw(rng)
                shifted_score = base_score + score_shifts[(index, bucket, result_key)]
                sampler = samplers[(bucket, result_key)]
                score = _round_half(_clamp(shifted_score, sampler.minimum, sampler.maximum))
                simulation_totals[index] += score
                bucket_counts[index][bucket] += 1
                if won:
                    game_wins[index][game_index] += 1
                    simulation_wins[index] += 1

        for index, row in enumerate(roster):
            win_count_distribution[index][simulation_wins[index]] += 1
            totals[index].append(_round_half(simulation_totals[index]))

    predictions = []
    player_history_games: dict[str, float] = defaultdict(float)
    for (player_id, _), stats in history["player_win_stats"].items():
        player_history_games[player_id] += float(stats.get("games") or 0.0)
    team_history_games: dict[str, float] = defaultdict(float)
    for (team_id, _), stats in history["team_win_stats"].items():
        team_history_games[team_id] += float(stats.get("games") or 0.0)

    for index, row in enumerate(roster):
        auto_totals = totals[index]
        auto_expected_total = sum(auto_totals) / simulations
        override = row.get("manual_total_override")
        final_totals = auto_totals
        if override not in (None, ""):
            final_totals = [_round_half(value + float(override)) for value in auto_totals]
        expected_total = sum(final_totals) / simulations
        game_probabilities = [round(count / simulations, 4) for count in game_wins[index]]
        win_distribution = [
            {
                "wins": wins,
                "probability": round(count / simulations, 4),
                "display": f"{count / simulations:.1%}",
            }
            for wins, count in enumerate(win_count_distribution[index])
        ]
        history_games = player_history_games.get(str(row.get("player_id") or ""), 0.0)
        team_games = team_history_games.get(str(row.get("team_id") or ""), 0.0)
        confidence = "较高" if history_games >= 9 else ("中等" if history_games >= 3 else "偏低")
        player_id = str(row.get("player_id") or row.get("scenario_player_id") or f"scenario-player-{index + 1}")
        predictions.append(
            {
                "rank": 0,
                "seat": index + 1,
                "player_id": player_id,
                "player_name": str(row.get("player_name") or player_id),
                "profile_href": str(row.get("profile_href") or ""),
                "team_id": str(row.get("team_id") or ""),
                "team_name": str(row.get("team_name") or ""),
                "model_source": (
                    "player_history"
                    if history_games > 0
                    else ("team_history" if team_games > 0 else "population_prior")
                ),
                "confidence": confidence,
                "match_count": 3,
                "game_win_probabilities": game_probabilities,
                "game_win_displays": [f"{value:.1%}" for value in game_probabilities],
                "expected_wins": round(sum(game_probabilities), 2),
                "win_count_probabilities": win_distribution,
                "auto_expected_total": f"{auto_expected_total:.2f}",
                "expected_total": f"{expected_total:.2f}",
                "expected_points": f"{expected_total:.2f}",
                "average_expected_points": f"{expected_total / 3.0:.2f}",
                "manual_override_applied": override not in (None, ""),
                "manual_total_override": float(override) if override not in (None, "") else None,
                "market_probabilities": _market_payload(final_totals),
                "identity_probabilities": {
                    key: round(value / (simulations * 3.0), 4)
                    for key, value in bucket_counts[index].items()
                },
            }
        )

    predictions.sort(
        key=lambda item: (-float(item["expected_total"]), item["player_name"])
    )
    for rank, item in enumerate(predictions, start=1):
        item["rank"] = rank
    return {
        "predictions": predictions,
        "model_metadata": {
            "version": MODEL_VERSION,
            "score_basis": "points_earned_minus_adjustment_points",
            "simulations": simulations,
            "seed_competition": SEED_COMPETITION,
            "seed_season": SEED_SEASON,
            "seed_match_count": history["seed_match_count"],
            "seed_player_day_count": history["seed_player_day_count"],
            "seed_average_daily_total": round(history["seed_average_daily_total"], 4),
            "seed_market_hit_counts": history["seed_market_hit_counts"],
            "seed_werewolf_wins": history["seed_werewolf_wins"],
            "seed_villager_wins": history["seed_villager_wins"],
            "rolling_match_count": history["rolling_match_count"],
            "rolling_sample_count": history["rolling_sample_count"],
            "rolling_share": round(history["rolling_share"], 4),
            "werewolf_win_prior": round(history["wolf_prior"], 4),
        },
        "market_definitions": list(MARKET_DEFINITIONS),
    }
