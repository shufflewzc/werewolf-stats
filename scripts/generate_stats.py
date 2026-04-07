#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from validate_data import validate_repository


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
CHINA_TZ = ZoneInfo("Asia/Shanghai")
BOOTSTRAP_CSS_URL = (
    "https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css"
)
CAMP_TO_CHINESE = {
    "villagers": "好人阵营",
    "werewolves": "狼人阵营",
    "third_party": "第三方阵营",
    "draw": "平局",
}
STAGE_TO_CHINESE = {
    "regular_season": "常规赛",
    "playoffs": "季后赛",
    "finals": "总决赛",
    "showmatch": "表演赛",
}
RESULT_TO_CHINESE = {
    "win": "胜",
    "loss": "负",
    "draw": "平",
}
STANCE_TO_CHINESE = {
    "villagers": "站好人",
    "werewolves": "站狼人",
    "third_party": "站第三方",
    "none": "未站边",
}


def safe_rate(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def to_chinese_camp(value: str) -> str:
    return CAMP_TO_CHINESE.get(value, value)


def to_chinese_stage(value: str) -> str:
    return STAGE_TO_CHINESE.get(value, value)


def to_chinese_result(value: str) -> str:
    return RESULT_TO_CHINESE.get(value, value)


def to_chinese_stance(value: str) -> str:
    return STANCE_TO_CHINESE.get(value, value)


def china_timestamp() -> str:
    return datetime.now(CHINA_TZ).replace(microsecond=0).isoformat()


def china_timestamp_label(value: str) -> str:
    return value.replace("T", " ").replace("+08:00", " 中国时间")


def match_sort_key(match: dict[str, Any]) -> tuple[Any, ...]:
    return (match["played_on"], match["round"], match["game_no"], match["match_id"])


def get_match_competition_name(match: dict[str, Any]) -> str:
    competition_name = match.get("competition_name")
    if isinstance(competition_name, str) and competition_name.strip():
        return competition_name.strip()

    season = match.get("season")
    if isinstance(season, str) and season.strip():
        return season.strip()
    return "未分类赛事"


def list_competitions(data: dict[str, Any]) -> list[str]:
    competitions: list[str] = []
    seen: set[str] = set()

    for match in sorted(data["matches"], key=match_sort_key, reverse=True):
        competition_name = get_match_competition_name(match)
        if competition_name not in seen:
            seen.add(competition_name)
            competitions.append(competition_name)

    return competitions


def filter_matches(
    data: dict[str, Any], competition_name: str | None = None
) -> list[dict[str, Any]]:
    if not competition_name:
        return list(data["matches"])
    return [
        match
        for match in data["matches"]
        if get_match_competition_name(match) == competition_name
    ]


def resolve_player_team_context(
    player: dict[str, Any],
    teams: dict[str, dict[str, Any]],
    matches: list[dict[str, Any]],
) -> tuple[str, str, list[str]]:
    ordered_team_ids: list[str] = []

    for match in sorted(matches, key=match_sort_key, reverse=True):
        for entry in match["players"]:
            if entry["player_id"] != player["player_id"]:
                continue
            if entry["team_id"] not in ordered_team_ids:
                ordered_team_ids.append(entry["team_id"])

    if not ordered_team_ids:
        team_id = player["team_id"]
        team_name = teams.get(team_id, {}).get("name", team_id)
        return team_id, team_name, [team_name]

    team_names = [teams.get(team_id, {}).get("name", team_id) for team_id in ordered_team_ids]
    team_name = team_names[0] if len(team_names) == 1 else f"{team_names[0]} 等{len(team_names)}队"
    return ordered_team_ids[0], team_name, team_names


def build_player_rows(
    data: dict[str, Any], competition_name: str | None = None
) -> list[dict[str, Any]]:
    players = {player["player_id"]: player for player in data["players"]}
    teams = {team["team_id"]: team for team in data["teams"]}
    matches = filter_matches(data, competition_name)
    aggregates: dict[str, dict[str, Any]] = {}

    for player_id, player in players.items():
        team_id, team_name, team_names = resolve_player_team_context(player, teams, matches)
        aggregates[player_id] = {
            "player_id": player_id,
            "display_name": player["display_name"],
            "team_id": team_id,
            "team_name": team_name,
            "team_names": team_names,
            "current_team_id": player["team_id"],
            "current_team_name": teams[player["team_id"]]["name"],
            "photo": player["photo"],
            "games_played": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "survivals": 0,
            "stance_calls": 0,
            "correct_stances": 0,
            "points_earned_total": 0.0,
            "points_available_total": 0.0,
        }

    for match in matches:
        for entry in match["players"]:
            row = aggregates[entry["player_id"]]
            row["games_played"] += 1
            row["wins"] += 1 if entry["result"] == "win" else 0
            row["losses"] += 1 if entry["result"] == "loss" else 0
            row["draws"] += 1 if entry["result"] == "draw" else 0
            row["survivals"] += 1 if entry["survived"] else 0
            row["points_earned_total"] += float(entry["points_earned"])
            row["points_available_total"] += float(entry["points_available"])

            if entry["stance_pick"] != "none":
                row["stance_calls"] += 1
                row["correct_stances"] += 1 if entry["stance_correct"] else 0

    leaderboard: list[dict[str, Any]] = []
    for row in aggregates.values():
        games_played = row["games_played"]
        win_rate = safe_rate(row["wins"], games_played)
        stance_rate = safe_rate(row["correct_stances"], row["stance_calls"])
        score_rate = safe_rate(
            row["points_earned_total"], row["points_available_total"]
        )
        survival_rate = safe_rate(row["survivals"], games_played)
        average_points = (
            round(row["points_earned_total"] / games_played, 2) if games_played else 0.0
        )

        leaderboard.append(
            {
                **row,
                "points_earned_total": round(row["points_earned_total"], 2),
                "points_available_total": round(row["points_available_total"], 2),
                "win_rate": win_rate,
                "stance_rate": stance_rate,
                "score_rate": score_rate,
                "average_points": average_points,
                "survival_rate": survival_rate,
                "record": f"{row['wins']}-{row['losses']}-{row['draws']}",
            }
        )

    leaderboard.sort(
        key=lambda item: (
            -item["score_rate"],
            -item["win_rate"],
            -item["stance_rate"],
            -item["average_points"],
            item["display_name"],
        )
    )

    for index, row in enumerate(leaderboard, start=1):
        row["rank"] = index

    return leaderboard


def build_team_rows(
    data: dict[str, Any], competition_name: str | None = None
) -> list[dict[str, Any]]:
    teams = {team["team_id"]: team for team in data["teams"]}
    matches = filter_matches(data, competition_name)
    aggregates: dict[str, dict[str, Any]] = {}
    represented_players: dict[str, set[str]] = {}

    for team_id, team in teams.items():
        represented_players[team_id] = set()
        aggregates[team_id] = {
            "team_id": team_id,
            "name": team["name"],
            "short_name": team["short_name"],
            "logo": team["logo"],
            "player_count": len(team["members"]),
            "matches_represented": 0,
            "player_appearances": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "stance_calls": 0,
            "correct_stances": 0,
            "points_earned_total": 0.0,
            "points_available_total": 0.0,
        }

    for match in matches:
        teams_in_match = set()
        for entry in match["players"]:
            row = aggregates[entry["team_id"]]
            row["player_appearances"] += 1
            represented_players[entry["team_id"]].add(entry["player_id"])
            row["wins"] += 1 if entry["result"] == "win" else 0
            row["losses"] += 1 if entry["result"] == "loss" else 0
            row["draws"] += 1 if entry["result"] == "draw" else 0
            row["points_earned_total"] += float(entry["points_earned"])
            row["points_available_total"] += float(entry["points_available"])
            if entry["stance_pick"] != "none":
                row["stance_calls"] += 1
                row["correct_stances"] += 1 if entry["stance_correct"] else 0
            teams_in_match.add(entry["team_id"])

        for team_id in teams_in_match:
            aggregates[team_id]["matches_represented"] += 1

    summary: list[dict[str, Any]] = []
    for row in aggregates.values():
        appearances = row["player_appearances"]
        participating_count = len(represented_players[row["team_id"]])
        summary.append(
            {
                **row,
                "player_count": participating_count if participating_count else row["player_count"],
                "represented_player_ids": sorted(represented_players[row["team_id"]]),
                "points_earned_total": round(row["points_earned_total"], 2),
                "points_available_total": round(row["points_available_total"], 2),
                "win_rate": safe_rate(row["wins"], appearances),
                "stance_rate": safe_rate(row["correct_stances"], row["stance_calls"]),
                "score_rate": safe_rate(
                    row["points_earned_total"], row["points_available_total"]
                ),
                "average_points": round(row["points_earned_total"] / appearances, 2)
                if appearances
                else 0.0,
            }
        )

    summary.sort(
        key=lambda item: (
            -item["score_rate"],
            -item["win_rate"],
            -item["stance_rate"],
            item["name"],
        )
    )

    for index, row in enumerate(summary, start=1):
        row["rank"] = index

    return summary


def build_match_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    teams = {team["team_id"]: team for team in data["teams"]}
    rows: list[dict[str, Any]] = []

    for match in sorted(
        data["matches"],
        key=match_sort_key,
        reverse=True,
    ):
        team_totals: dict[str, float] = {}
        for entry in match["players"]:
            team_totals.setdefault(entry["team_id"], 0.0)
            team_totals[entry["team_id"]] += float(entry["points_earned"])

        ordered_totals = sorted(
            team_totals.items(),
            key=lambda item: (-item[1], teams[item[0]]["name"]),
        )

        rows.append(
            {
                "match_id": match["match_id"],
                "competition_name": get_match_competition_name(match),
                "season": match["season"],
                "stage_label": to_chinese_stage(match["stage"]),
                "round": match["round"],
                "game_no": match["game_no"],
                "played_on": match["played_on"],
                "table_label": match["table_label"],
                "format": match["format"],
                "duration_minutes": match["duration_minutes"],
                "winning_camp_label": to_chinese_camp(match["winning_camp"]),
                "team_scores": [
                    {
                        "team_id": team_id,
                        "team_name": teams[team_id]["name"],
                        "score": round(score, 2),
                    }
                    for team_id, score in ordered_totals
                ],
            }
        )

    return rows


def build_player_details(
    data: dict[str, Any],
    player_rows: list[dict[str, Any]],
    competition_name: str | None = None,
) -> dict[str, dict[str, Any]]:
    player_lookup = {player["player_id"]: player for player in data["players"]}
    row_lookup = {row["player_id"]: row for row in player_rows}
    matches = filter_matches(data, competition_name)
    competition_rows = {
        name: {
            row["player_id"]: row
            for row in build_player_rows(data, name)
            if row["games_played"] > 0
        }
        for name in list_competitions(data)
    }
    details: dict[str, dict[str, Any]] = {}

    for player_id, player in player_lookup.items():
        row = row_lookup[player_id]
        history: list[dict[str, Any]] = []
        roles: dict[str, int] = {}

        for match in sorted(
            matches,
            key=match_sort_key,
            reverse=True,
        ):
            for entry in match["players"]:
                if entry["player_id"] != player_id:
                    continue
                roles[entry["role"]] = roles.get(entry["role"], 0) + 1
                history.append(
                    {
                        "match_id": match["match_id"],
                        "competition_name": get_match_competition_name(match),
                        "season": match["season"],
                        "stage_label": to_chinese_stage(match["stage"]),
                        "round": match["round"],
                        "game_no": match["game_no"],
                        "played_on": match["played_on"],
                        "table_label": match["table_label"],
                        "role": entry["role"],
                        "camp_label": to_chinese_camp(entry["camp"]),
                        "result_label": to_chinese_result(entry["result"]),
                        "survived_label": "存活" if entry["survived"] else "出局",
                        "points_earned": round(float(entry["points_earned"]), 2),
                        "points_available": round(float(entry["points_available"]), 2),
                        "stance_pick_label": to_chinese_stance(entry["stance_pick"]),
                        "stance_correct_label": "正确" if entry["stance_correct"] else "错误",
                        "notes": entry["notes"],
                    }
                )

        role_rows = [
            {"role": role, "games": count}
            for role, count in sorted(roles.items(), key=lambda item: (-item[1], item[0]))
        ]
        competition_stats = []
        for name in list_competitions(data):
            competition_row = competition_rows.get(name, {}).get(player_id)
            if not competition_row:
                continue
            competition_stats.append(
                {
                    "competition_name": name,
                    "team_name": competition_row["team_name"],
                    "games_played": competition_row["games_played"],
                    "record": competition_row["record"],
                    "win_rate": format_pct(competition_row["win_rate"]),
                    "stance_rate": format_pct(competition_row["stance_rate"]),
                    "score_rate": format_pct(competition_row["score_rate"]),
                    "average_points": f"{competition_row['average_points']:.2f}",
                }
            )

        details[player_id] = {
            "player_id": player_id,
            "display_name": player["display_name"],
            "team_name": row["team_name"],
            "rank": row["rank"],
            "aliases": player["aliases"],
            "joined_on": player["joined_on"],
            "photo": player["photo"],
            "notes": player["notes"],
            "record": row["record"],
            "games_played": row["games_played"],
            "wins": row["wins"],
            "losses": row["losses"],
            "draws": row["draws"],
            "win_rate": format_pct(row["win_rate"]),
            "stance_rate": format_pct(row["stance_rate"]),
            "score_rate": format_pct(row["score_rate"]),
            "survival_rate": format_pct(row["survival_rate"]),
            "average_points": f"{row['average_points']:.2f}",
            "points_total": f"{row['points_earned_total']:.2f}",
            "points_cap": f"{row['points_available_total']:.2f}",
            "correct_stances": row["correct_stances"],
            "stance_calls": row["stance_calls"],
            "survivals": row["survivals"],
            "roles": role_rows,
            "history": history,
            "competition_stats": competition_stats,
        }

    return details


def render_player_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# 队员排行榜",
        "",
        "| 排名 | 队员 | 战队 | 出场 | 战绩 | 胜率 | 站边率 | 得分率 | 场均得分 | 存活率 |",
        "| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    for row in rows:
        lines.append(
            "| "
            f"{row['rank']} | "
            f"{row['display_name']} | "
            f"{row['team_name']} | "
            f"{row['games_played']} | "
            f"{row['record']} | "
            f"{format_pct(row['win_rate'])} | "
            f"{format_pct(row['stance_rate'])} | "
            f"{format_pct(row['score_rate'])} | "
            f"{row['average_points']:.2f} | "
            f"{format_pct(row['survival_rate'])} |"
        )

    lines.append("")
    return "\n".join(lines)


def render_team_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# 战队汇总",
        "",
        "| 排名 | 战队 | 队员数 | 对局场次 | 队员出场 | 胜率 | 站边率 | 得分率 | 场均得分 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for row in rows:
        lines.append(
            "| "
            f"{row['rank']} | "
            f"{row['name']} | "
            f"{row['player_count']} | "
            f"{row['matches_represented']} | "
            f"{row['player_appearances']} | "
            f"{format_pct(row['win_rate'])} | "
            f"{format_pct(row['stance_rate'])} | "
            f"{format_pct(row['score_rate'])} | "
            f"{row['average_points']:.2f} |"
        )

    lines.append("")
    return "\n".join(lines)


def render_stat_card(title: str, value: str, detail: str) -> str:
    return f"""
    <div class="col-6 col-xl-3">
      <div class="card stat-card h-100 border-0 shadow-sm">
        <div class="card-body">
          <div class="stat-label">{escape(title)}</div>
          <div class="stat-value">{escape(value)}</div>
          <div class="stat-detail">{escape(detail)}</div>
        </div>
      </div>
    </div>
    """


def render_dashboard_html(
    player_rows: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
    match_rows: list[dict[str, Any]],
    player_details: dict[str, dict[str, Any]],
    data: dict[str, Any],
    generated_at: str,
) -> str:
    top_player = player_rows[0] if player_rows else None
    top_team = team_rows[0] if team_rows else None

    stat_cards = "\n".join(
        [
            render_stat_card("战队数量", str(len(data["teams"])), "当前已录入战队"),
            render_stat_card("队员数量", str(len(data["players"])), "全部可统计队员"),
            render_stat_card("对局数量", str(len(data["matches"])), "标准化赛事记录"),
            render_stat_card(
                "当前榜首",
                top_player["display_name"] if top_player else "-",
                top_player["team_name"] if top_player else "暂无数据",
            ),
        ]
    )

    top_player_cards = "\n".join(
        f"""
        <div class="col-12 col-md-6 col-xl-4">
          <button type="button" class="card player-card player-trigger h-100 border-0 shadow-sm text-start w-100" data-player-id="{escape(row['player_id'])}">
            <div class="card-body">
              <div class="d-flex align-items-start justify-content-between gap-3">
                <div>
                  <div class="eyebrow">第 {row['rank']} 名</div>
                  <h3 class="h5 mb-1">{escape(row['display_name'])}</h3>
                  <div class="text-secondary small">{escape(row['team_name'])}</div>
                </div>
                <div class="rank-pill">第{row['rank']}名</div>
              </div>
              <div class="metric-grid mt-4">
                <div>
                  <span>胜率</span>
                  <strong>{format_pct(row['win_rate'])}</strong>
                </div>
                <div>
                  <span>站边率</span>
                  <strong>{format_pct(row['stance_rate'])}</strong>
                </div>
                <div>
                  <span>得分率</span>
                  <strong>{format_pct(row['score_rate'])}</strong>
                </div>
                <div>
                  <span>场均得分</span>
                  <strong>{row['average_points']:.2f}</strong>
                </div>
              </div>
              <div class="open-hint mt-3">点击查看队员详情</div>
            </div>
          </button>
        </div>
        """
        for row in player_rows[:6]
    )

    team_cards = "\n".join(
        f"""
        <div class="col-12 col-lg-6">
          <div class="card team-card h-100 border-0 shadow-sm">
            <div class="card-body">
              <div class="d-flex align-items-start justify-content-between gap-3">
                <div>
                  <div class="eyebrow">战队第 {row['rank']} 名</div>
                  <h3 class="h5 mb-1">{escape(row['name'])}</h3>
                  <div class="text-secondary small">{row['player_count']} 名队员</div>
                </div>
                <div class="rank-pill">第{row['rank']}名</div>
              </div>
              <div class="metric-grid mt-4">
                <div>
                  <span>胜率</span>
                  <strong>{format_pct(row['win_rate'])}</strong>
                </div>
                <div>
                  <span>站边率</span>
                  <strong>{format_pct(row['stance_rate'])}</strong>
                </div>
                <div>
                  <span>得分率</span>
                  <strong>{format_pct(row['score_rate'])}</strong>
                </div>
                <div>
                  <span>场均得分</span>
                  <strong>{row['average_points']:.2f}</strong>
                </div>
              </div>
            </div>
          </div>
        </div>
        """
        for row in team_rows
    )

    recent_match_cards = "\n".join(
        f"""
        <div class="col-12 col-lg-6">
          <div class="card match-card h-100 border-0 shadow-sm">
            <div class="card-body">
              <div class="d-flex flex-wrap align-items-center justify-content-between gap-3">
                <div>
                  <div class="eyebrow">{escape(match['played_on'])} · 第 {match['round']} 轮 第 {match['game_no']} 局</div>
                  <h3 class="h5 mb-1">{escape(match['season'])}</h3>
                  <div class="text-secondary small">{escape(match['stage_label'])} · {escape(match['table_label'])} · {escape(match['format'])} · {match['duration_minutes']} 分钟</div>
                </div>
                <span class="badge rounded-pill text-bg-dark">胜利阵营：{escape(match['winning_camp_label'])}</span>
              </div>
              <div class="scoreboard mt-4">
                {"".join(
                    f'<div class="score-row"><span>{escape(score["team_name"])}</span><strong>{score["score"]:.1f}</strong></div>'
                    for score in match["team_scores"]
                )}
              </div>
            </div>
          </div>
        </div>
        """
        for match in match_rows[:4]
    )

    player_table_rows = "\n".join(
        f"""
        <tr class="player-row player-trigger" data-player-id="{escape(row['player_id'])}" tabindex="0" role="button">
          <td>{row['rank']}</td>
          <td>
            <div class="fw-semibold">{escape(row['display_name'])}</div>
          </td>
          <td>{escape(row['team_name'])}</td>
          <td>{row['games_played']}</td>
          <td>{escape(row['record'])}</td>
          <td>{format_pct(row['win_rate'])}</td>
          <td>{format_pct(row['stance_rate'])}</td>
          <td>{format_pct(row['score_rate'])}</td>
          <td>{row['average_points']:.2f}</td>
          <td>{format_pct(row['survival_rate'])}</td>
        </tr>
        """
        for row in player_rows
    )

    team_table_rows = "\n".join(
        f"""
        <tr>
          <td>{row['rank']}</td>
          <td>{escape(row['name'])}</td>
          <td>{row['player_count']}</td>
          <td>{row['matches_represented']}</td>
          <td>{row['player_appearances']}</td>
          <td>{format_pct(row['win_rate'])}</td>
          <td>{format_pct(row['stance_rate'])}</td>
          <td>{format_pct(row['score_rate'])}</td>
          <td>{row['average_points']:.2f}</td>
        </tr>
        """
        for row in team_rows
    )

    generated_display = china_timestamp_label(generated_at)
    hero_team = top_team["name"] if top_team else "-"
    hero_player = top_player["display_name"] if top_player else "-"
    details_json = json.dumps(player_details, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>狼人杀数据看板</title>
    <link rel="stylesheet" href="{BOOTSTRAP_CSS_URL}">
    <style>
      :root {{
        --bg: #f3f5ef;
        --surface: rgba(255, 255, 255, 0.9);
        --ink: #1d2a22;
        --muted: #5d6b61;
        --accent: #9e2a2b;
        --accent-dark: #5c1a1b;
        --line: rgba(34, 48, 40, 0.08);
      }}

      body {{
        min-height: 100vh;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(158, 42, 43, 0.16), transparent 32%),
          radial-gradient(circle at top right, rgba(33, 84, 58, 0.12), transparent 28%),
          linear-gradient(180deg, #f7f3eb 0%, var(--bg) 100%);
      }}

      .dashboard-shell {{
        max-width: 1320px;
      }}

      .hero {{
        position: relative;
        overflow: hidden;
        background: linear-gradient(135deg, rgba(27, 35, 30, 0.96), rgba(74, 27, 28, 0.93));
        color: #fff7f2;
        border-radius: 28px;
      }}

      .hero::after {{
        content: "";
        position: absolute;
        inset: auto -10% -30% auto;
        width: 260px;
        height: 260px;
        background: radial-gradient(circle, rgba(255, 255, 255, 0.16), transparent 68%);
      }}

      .eyebrow {{
        letter-spacing: 0.14em;
        text-transform: uppercase;
        font-size: 0.72rem;
        color: rgba(255, 248, 243, 0.72);
      }}

      .hero h1 {{
        font-size: clamp(2rem, 5vw, 4.2rem);
        line-height: 0.95;
        letter-spacing: -0.04em;
      }}

      .hero-copy {{
        max-width: 36rem;
        color: rgba(255, 248, 243, 0.82);
      }}

      .glass-panel {{
        background: rgba(255, 250, 247, 0.12);
        border: 1px solid rgba(255, 248, 243, 0.16);
        border-radius: 20px;
        backdrop-filter: blur(8px);
      }}

      .stat-card,
      .player-card,
      .team-card,
      .match-card,
      .table-panel,
      .detail-panel {{
        background: var(--surface);
        border-radius: 24px;
      }}

      .player-card {{
        transition: transform 0.18s ease, box-shadow 0.18s ease;
      }}

      .player-card:hover,
      .player-card:focus-visible {{
        transform: translateY(-4px);
        box-shadow: 0 1rem 2rem rgba(29, 42, 34, 0.12) !important;
      }}

      .player-trigger {{
        cursor: pointer;
      }}

      .open-hint {{
        color: var(--accent-dark);
        font-size: 0.9rem;
        font-weight: 600;
      }}

      .stat-label {{
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: var(--muted);
      }}

      .stat-value {{
        margin-top: 0.4rem;
        font-size: clamp(1.7rem, 4vw, 2.5rem);
        line-height: 1;
        font-weight: 700;
      }}

      .stat-detail {{
        margin-top: 0.5rem;
        color: var(--muted);
        font-size: 0.94rem;
      }}

      .rank-pill {{
        min-width: 4.4rem;
        padding: 0.4rem 0.75rem;
        border-radius: 999px;
        background: linear-gradient(135deg, var(--accent), var(--accent-dark));
        color: white;
        text-align: center;
        font-weight: 700;
      }}

      .metric-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 1rem 1.25rem;
      }}

      .metric-grid span {{
        display: block;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--muted);
      }}

      .metric-grid strong {{
        font-size: 1.2rem;
      }}

      .scoreboard {{
        display: grid;
        gap: 0.85rem;
      }}

      .score-row {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.9rem 1rem;
        background: rgba(29, 42, 34, 0.04);
        border-radius: 16px;
      }}

      .score-row strong {{
        font-size: 1.2rem;
      }}

      .section-title {{
        font-size: clamp(1.35rem, 3vw, 2rem);
        letter-spacing: -0.03em;
      }}

      .section-copy {{
        color: var(--muted);
        max-width: 38rem;
      }}

      .table {{
        --bs-table-bg: transparent;
        --bs-table-border-color: var(--line);
        margin-bottom: 0;
      }}

      .table thead th {{
        white-space: nowrap;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
      }}

      .player-row:hover {{
        background: rgba(158, 42, 43, 0.05);
      }}

      .detail-overlay {{
        position: fixed;
        inset: 0;
        display: none;
        align-items: center;
        justify-content: center;
        padding: 1rem;
        background: rgba(16, 22, 19, 0.56);
        z-index: 1050;
      }}

      .detail-overlay.is-open {{
        display: flex;
      }}

      .detail-shell {{
        width: min(1100px, 100%);
        max-height: min(92vh, 980px);
        overflow: auto;
        border-radius: 28px;
        box-shadow: 0 1.5rem 3rem rgba(18, 22, 19, 0.2);
      }}

      .detail-hero {{
        background: linear-gradient(135deg, rgba(27, 35, 30, 0.98), rgba(74, 27, 28, 0.93));
        color: #fff7f2;
        border-radius: 28px 28px 0 0;
      }}

      .avatar-chip {{
        width: 84px;
        height: 84px;
        border-radius: 50%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: rgba(255, 255, 255, 0.14);
        border: 1px solid rgba(255, 255, 255, 0.14);
        font-size: 2rem;
        font-weight: 700;
      }}

      .close-button {{
        border: 0;
        border-radius: 999px;
        width: 2.75rem;
        height: 2.75rem;
        background: rgba(255, 255, 255, 0.16);
        color: white;
        font-size: 1.25rem;
      }}

      .detail-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 1rem;
      }}

      .detail-metric {{
        padding: 1rem;
        border-radius: 18px;
        background: rgba(29, 42, 34, 0.04);
      }}

      .detail-metric span {{
        display: block;
        color: var(--muted);
        font-size: 0.82rem;
      }}

      .detail-metric strong {{
        display: block;
        margin-top: 0.35rem;
        font-size: 1.35rem;
      }}

      .history-card {{
        padding: 1rem;
        border-radius: 18px;
        background: rgba(29, 42, 34, 0.04);
      }}

      .history-meta {{
        color: var(--muted);
        font-size: 0.9rem;
      }}

      .role-badges {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
      }}

      .role-badge {{
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.45rem 0.7rem;
        border-radius: 999px;
        background: rgba(29, 42, 34, 0.07);
        color: var(--ink);
        font-size: 0.9rem;
      }}

      .footer-note {{
        color: var(--muted);
        font-size: 0.92rem;
      }}

      @media (max-width: 767.98px) {{
        .hero {{
          border-radius: 22px;
        }}

        .metric-grid,
        .detail-grid {{
          grid-template-columns: 1fr 1fr;
        }}

        .table-panel,
        .detail-shell,
        .detail-hero {{
          border-radius: 20px;
        }}

        .detail-shell {{
          max-height: 94vh;
        }}
      }}

      @media (max-width: 575.98px) {{
        .detail-grid {{
          grid-template-columns: 1fr;
        }}

        .avatar-chip {{
          width: 72px;
          height: 72px;
          font-size: 1.7rem;
        }}
      }}
    </style>
  </head>
  <body>
    <div class="container-fluid px-3 px-md-4 px-xl-5 py-4 py-lg-5">
      <div class="dashboard-shell mx-auto">
        <section class="hero p-4 p-md-5 shadow-lg mb-4 mb-lg-5">
          <div class="row g-4 align-items-end">
            <div class="col-12 col-xl-7">
              <div class="eyebrow mb-3">狼人杀赛事数据看板</div>
              <h1 class="mb-3">像职业联赛一样看<br>狼人杀战队数据</h1>
              <p class="hero-copy mb-4">
                这是一页式、响应式的赛事数据面板。当前榜首队员是 {escape(hero_player)}，
                战队表现第一是 {escape(hero_team)}，手机和电脑都能顺畅浏览。
              </p>
              <div class="d-flex flex-wrap gap-2">
                <span class="badge rounded-pill text-bg-light px-3 py-2">响应式仪表盘</span>
                <span class="badge rounded-pill text-bg-light px-3 py-2">生成时间：{escape(generated_display)}</span>
              </div>
            </div>
            <div class="col-12 col-xl-5">
              <div class="glass-panel p-4">
                <div class="eyebrow mb-2">当前领跑</div>
                <div class="d-flex justify-content-between gap-3 mb-3">
                  <div>
                    <div class="small text-white-50">队员榜首</div>
                    <div class="fs-4 fw-semibold">{escape(hero_player)}</div>
                  </div>
                  <div class="text-end">
                    <div class="small text-white-50">战队榜首</div>
                    <div class="fs-4 fw-semibold">{escape(hero_team)}</div>
                  </div>
                </div>
                <div class="small text-white-50">
                  数据来自本仓库中的战队、队员与赛事记录文件，统计口径包含胜率、站边率、得分率、场均得分和存活率。
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="mb-4 mb-lg-5">
          <div class="row g-3 g-lg-4">
            {stat_cards}
          </div>
        </section>

        <section class="mb-4 mb-lg-5">
          <div class="d-flex flex-column flex-lg-row align-items-lg-end justify-content-between gap-3 mb-3 mb-lg-4">
            <div>
              <h2 class="section-title mb-2">队员榜前列</h2>
              <p class="section-copy mb-0">按得分率、胜率、站边率和场均得分综合排序，先看最有明星相的队员。</p>
            </div>
          </div>
          <div class="row g-3 g-lg-4">
            {top_player_cards}
          </div>
        </section>

        <section class="mb-4 mb-lg-5">
          <div class="d-flex flex-column flex-lg-row align-items-lg-end justify-content-between gap-3 mb-3 mb-lg-4">
            <div>
              <h2 class="section-title mb-2">战队概览</h2>
              <p class="section-copy mb-0">战队汇总按全部队员出场表现聚合，更适合展示整体训练和赛季状态。</p>
            </div>
          </div>
          <div class="row g-3 g-lg-4">
            {team_cards}
          </div>
        </section>

        <section class="mb-4 mb-lg-5">
          <div class="d-flex flex-column flex-lg-row align-items-lg-end justify-content-between gap-3 mb-3 mb-lg-4">
            <div>
              <h2 class="section-title mb-2">最近对局</h2>
              <p class="section-copy mb-0">最近对局会显示胜利阵营和各战队本局累计得分，方便快速回顾走势。</p>
            </div>
          </div>
          <div class="row g-3 g-lg-4">
            {recent_match_cards}
          </div>
        </section>

        <section class="mb-4 mb-lg-5">
          <div class="table-panel p-3 p-lg-4 shadow-sm">
            <div class="d-flex flex-column flex-lg-row align-items-lg-end justify-content-between gap-3 mb-3">
              <div>
                <h2 class="section-title mb-2">完整队员排行榜</h2>
                <p class="section-copy mb-0">点击任意队员卡片或表格行，可以查看个人详情、最近对局和角色分布。</p>
              </div>
            </div>
            <div class="table-responsive">
              <table class="table align-middle">
                <thead>
                  <tr>
                    <th>排名</th>
                    <th>队员</th>
                    <th>战队</th>
                    <th>出场</th>
                    <th>战绩</th>
                    <th>胜率</th>
                    <th>站边率</th>
                    <th>得分率</th>
                    <th>场均得分</th>
                    <th>存活率</th>
                  </tr>
                </thead>
                <tbody>
                  {player_table_rows}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section class="mb-4">
          <div class="table-panel p-3 p-lg-4 shadow-sm">
            <div class="d-flex flex-column flex-lg-row align-items-lg-end justify-content-between gap-3 mb-3">
              <div>
                <h2 class="section-title mb-2">战队汇总表</h2>
                <p class="section-copy mb-0">如果你后面要补战绩榜、季后赛图或单角色榜，这张表可以继续作为主页概览层。</p>
              </div>
            </div>
            <div class="table-responsive">
              <table class="table align-middle">
                <thead>
                  <tr>
                    <th>排名</th>
                    <th>战队</th>
                    <th>队员数</th>
                    <th>对局场次</th>
                    <th>队员出场</th>
                    <th>胜率</th>
                    <th>站边率</th>
                    <th>得分率</th>
                    <th>场均得分</th>
                  </tr>
                </thead>
                <tbody>
                  {team_table_rows}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <footer class="pt-2 pb-4">
          <div class="footer-note">
            当前页面为响应式中文仪表盘，支持点击队员查看个人数据，适合电脑和手机浏览。
          </div>
        </footer>
      </div>
    </div>

    <div class="detail-overlay" id="队员详情层" aria-hidden="true">
      <div class="detail-shell detail-panel">
        <div class="detail-hero p-4 p-md-5">
          <div class="d-flex align-items-start justify-content-between gap-3">
            <div class="d-flex align-items-center gap-3">
              <div class="avatar-chip" id="详情头像">星</div>
              <div>
                <div class="eyebrow mb-2" id="详情排名">第 1 名</div>
                <h2 class="h3 mb-1" id="详情姓名">队员姓名</h2>
                <div class="text-white-50" id="详情战队">所属战队</div>
              </div>
            </div>
            <button type="button" class="close-button" id="详情关闭按钮" aria-label="关闭详情">×</button>
          </div>
        </div>
        <div class="p-3 p-md-4 p-xl-5">
          <div class="row g-3 g-lg-4">
            <div class="col-12 col-xl-7">
              <div class="detail-grid">
                <div class="detail-metric">
                  <span>战绩</span>
                  <strong id="详情战绩">0-0-0</strong>
                </div>
                <div class="detail-metric">
                  <span>场均得分</span>
                  <strong id="详情场均得分">0.00</strong>
                </div>
                <div class="detail-metric">
                  <span>胜率</span>
                  <strong id="详情胜率">0.0%</strong>
                </div>
                <div class="detail-metric">
                  <span>站边率</span>
                  <strong id="详情站边率">0.0%</strong>
                </div>
                <div class="detail-metric">
                  <span>得分率</span>
                  <strong id="详情得分率">0.0%</strong>
                </div>
                <div class="detail-metric">
                  <span>存活率</span>
                  <strong id="详情存活率">0.0%</strong>
                </div>
              </div>
            </div>
            <div class="col-12 col-xl-5">
              <div class="detail-panel p-3 p-lg-4 h-100">
                <div class="eyebrow mb-2 text-secondary">队员资料</div>
                <div class="mb-2"><strong>别名：</strong><span id="详情别名">无</span></div>
                <div class="mb-2"><strong>入库日期：</strong><span id="详情入库日期">-</span></div>
                <div class="mb-2"><strong>照片路径：</strong><span id="详情照片路径">-</span></div>
                <div class="mb-0"><strong>备注：</strong><span id="详情备注">-</span></div>
              </div>
            </div>
            <div class="col-12 col-xl-4">
              <div class="detail-panel p-3 p-lg-4 h-100">
                <div class="eyebrow mb-3 text-secondary">角色分布</div>
                <div class="role-badges" id="详情角色分布"></div>
              </div>
            </div>
            <div class="col-12 col-xl-8">
              <div class="detail-panel p-3 p-lg-4 h-100">
                <div class="eyebrow mb-3 text-secondary">累计数据</div>
                <div class="detail-grid">
                  <div class="detail-metric">
                    <span>总得分</span>
                    <strong id="详情总得分">0.00</strong>
                  </div>
                  <div class="detail-metric">
                    <span>总满分</span>
                    <strong id="详情总满分">0.00</strong>
                  </div>
                  <div class="detail-metric">
                    <span>正确站边</span>
                    <strong id="详情正确站边">0</strong>
                  </div>
                  <div class="detail-metric">
                    <span>站边次数</span>
                    <strong id="详情站边次数">0</strong>
                  </div>
                  <div class="detail-metric">
                    <span>存活局数</span>
                    <strong id="详情存活局数">0</strong>
                  </div>
                  <div class="detail-metric">
                    <span>总出场</span>
                    <strong id="详情总出场">0</strong>
                  </div>
                </div>
              </div>
            </div>
            <div class="col-12">
              <div class="detail-panel p-3 p-lg-4">
                <div class="d-flex align-items-center justify-content-between gap-3 mb-3">
                  <div class="eyebrow text-secondary">最近对局</div>
                  <div class="small text-secondary">按最新比赛在前展示</div>
                </div>
                <div class="row g-3" id="详情对局历史"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <script>
      const 队员详情数据 = {details_json};
      const 详情层 = document.getElementById("队员详情层");
      const 详情关闭按钮 = document.getElementById("详情关闭按钮");

      function 设置文本(id, value) {{
        const 节点 = document.getElementById(id);
        if (节点) {{
          节点.textContent = value;
        }}
      }}

      function 渲染角色分布(角色列表) {{
        const 容器 = document.getElementById("详情角色分布");
        容器.innerHTML = "";
        if (!角色列表.length) {{
          容器.innerHTML = '<span class="text-secondary">暂无角色数据</span>';
          return;
        }}
        for (const 项 of 角色列表) {{
          const 标签 = document.createElement("span");
          标签.className = "role-badge";
          标签.textContent = `${{项.role}} · ${{项.games}}局`;
          容器.appendChild(标签);
        }}
      }}

      function 渲染对局历史(历史列表) {{
        const 容器 = document.getElementById("详情对局历史");
        容器.innerHTML = "";
        if (!历史列表.length) {{
          容器.innerHTML = '<div class="col-12 text-secondary">暂无对局历史</div>';
          return;
        }}
        for (const 对局 of 历史列表) {{
          const 卡片 = document.createElement("div");
          卡片.className = "col-12 col-lg-6";
          卡片.innerHTML = `
            <div class="history-card h-100">
              <div class="d-flex align-items-start justify-content-between gap-3 mb-2">
                <div>
                  <div class="fw-semibold">${{对局.season}}</div>
                  <div class="history-meta">${{对局.played_on}} · ${{对局.stage_label}} · 第${{对局.round}}轮第${{对局.game_no}}局</div>
                </div>
                <span class="badge rounded-pill text-bg-dark">${{对局.result_label}}</span>
              </div>
              <div class="small mb-2">角色：${{对局.role}} · 阵营：${{对局.camp_label}} · ${{对局.survived_label}}</div>
              <div class="small mb-2">站边：${{对局.stance_pick_label}} · 判断：${{对局.stance_correct_label}}</div>
              <div class="small mb-2">得分：${{对局.points_earned}} / ${{对局.points_available}}</div>
              <div class="small text-secondary">${{对局.notes}}</div>
            </div>
          `;
          容器.appendChild(卡片);
        }}
      }}

      function 打开队员详情(playerId) {{
        const 数据 = 队员详情数据[playerId];
        if (!数据) {{
          return;
        }}
        设置文本("详情头像", 数据.display_name.slice(0, 1));
        设置文本("详情排名", `第 ${{数据.rank}} 名`);
        设置文本("详情姓名", 数据.display_name);
        设置文本("详情战队", 数据.team_name);
        设置文本("详情战绩", 数据.record);
        设置文本("详情场均得分", 数据.average_points);
        设置文本("详情胜率", 数据.win_rate);
        设置文本("详情站边率", 数据.stance_rate);
        设置文本("详情得分率", 数据.score_rate);
        设置文本("详情存活率", 数据.survival_rate);
        设置文本("详情别名", 数据.aliases.length ? 数据.aliases.join("、") : "无");
        设置文本("详情入库日期", 数据.joined_on);
        设置文本("详情照片路径", 数据.photo);
        设置文本("详情备注", 数据.notes || "无");
        设置文本("详情总得分", 数据.points_total);
        设置文本("详情总满分", 数据.points_cap);
        设置文本("详情正确站边", String(数据.correct_stances));
        设置文本("详情站边次数", String(数据.stance_calls));
        设置文本("详情存活局数", String(数据.survivals));
        设置文本("详情总出场", String(数据.games_played));
        渲染角色分布(数据.roles);
        渲染对局历史(数据.history);
        详情层.classList.add("is-open");
        详情层.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";
      }}

      function 关闭队员详情() {{
        详情层.classList.remove("is-open");
        详情层.setAttribute("aria-hidden", "true");
        document.body.style.overflow = "";
      }}

      document.querySelectorAll(".player-trigger").forEach((节点) => {{
        节点.addEventListener("click", () => {{
          打开队员详情(节点.dataset.playerId);
        }});
        节点.addEventListener("keydown", (事件) => {{
          if (事件.key === "Enter" || 事件.key === " ") {{
            事件.preventDefault();
            打开队员详情(节点.dataset.playerId);
          }}
        }});
      }});

      详情关闭按钮.addEventListener("click", 关闭队员详情);
      详情层.addEventListener("click", (事件) => {{
        if (事件.target === 详情层) {{
          关闭队员详情();
        }}
      }});

      document.addEventListener("keydown", (事件) => {{
        if (事件.key === "Escape" && 详情层.classList.contains("is-open")) {{
          关闭队员详情();
        }}
      }});
    </script>
  </body>
</html>
"""


def main() -> int:
    errors, data = validate_repository()
    if errors:
        print("生成报表失败，原因是数据校验没有通过：", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    generated_at = china_timestamp()
    player_rows = build_player_rows(data)
    team_rows = build_team_rows(data)
    match_rows = build_match_rows(data)
    player_details = build_player_details(data, player_rows)

    player_payload = {
        "generated_at": generated_at,
        "leaderboard": player_rows,
        "player_details": player_details,
    }
    team_payload = {
        "generated_at": generated_at,
        "summary": team_rows,
    }

    write_json(REPORTS_DIR / "player_leaderboard.json", player_payload)
    write_json(REPORTS_DIR / "team_summary.json", team_payload)
    write_text(REPORTS_DIR / "player_leaderboard.md", render_player_markdown(player_rows))
    write_text(REPORTS_DIR / "team_summary.md", render_team_markdown(team_rows))
    write_text(
        REPORTS_DIR / "dashboard.html",
        render_dashboard_html(
            player_rows, team_rows, match_rows, player_details, data, generated_at
        ),
    )

    print("报表已生成：")
    print(f"- {REPORTS_DIR / 'player_leaderboard.json'}")
    print(f"- {REPORTS_DIR / 'player_leaderboard.md'}")
    print(f"- {REPORTS_DIR / 'team_summary.json'}")
    print(f"- {REPORTS_DIR / 'team_summary.md'}")
    print(f"- {REPORTS_DIR / 'dashboard.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
