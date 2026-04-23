from __future__ import annotations

import calendar
import json
from datetime import datetime, date

import web_app as legacy

Any = legacy.Any
CAMP_OPTIONS = legacy.CAMP_OPTIONS
DEFAULT_REGION_NAME = legacy.DEFAULT_REGION_NAME
RESULT_OPTIONS = legacy.RESULT_OPTIONS
RequestContext = legacy.RequestContext
STAGE_OPTIONS = legacy.STAGE_OPTIONS
build_scoped_path = legacy.build_scoped_path
build_competition_catalog_rows = legacy.build_competition_catalog_rows
build_filtered_data = legacy.build_filtered_data
build_player_rows = legacy.build_player_rows
build_region_switcher = legacy.build_region_switcher
build_series_manage_path = legacy.build_series_manage_path
build_series_season_switcher = legacy.build_series_season_switcher
build_series_switcher = legacy.build_series_switcher
build_series_topic_path = legacy.build_series_topic_path
build_team_rows = legacy.build_team_rows
build_competition_switcher = legacy.build_competition_switcher
build_season_switcher = legacy.build_season_switcher
build_match_day_path = legacy.build_match_day_path
append_alert_query = legacy.append_alert_query
account_role_label = legacy.account_role_label
can_access_series_management = legacy.can_access_series_management
can_manage_competition_catalog = legacy.can_manage_competition_catalog
can_manage_competition_seasons = legacy.can_manage_competition_seasons
can_manage_matches = legacy.can_manage_matches
can_manage_team = legacy.can_manage_team
escape = legacy.escape
format_datetime_local_label = legacy.format_datetime_local_label
format_pct = legacy.format_pct
form_value = legacy.form_value
get_selected_season = legacy.get_selected_season
get_series_entries_by_slug = legacy.get_series_entries_by_slug
get_match_competition_name = legacy.get_match_competition_name
get_nearest_match_day_label = legacy.get_nearest_match_day_label
get_scheduled_match_day_label = legacy.get_scheduled_match_day_label
is_match_counted_as_played = legacy.is_match_counted_as_played
get_season_entry = legacy.get_season_entry
get_season_status = legacy.get_season_status
get_series_entry_by_competition = legacy.get_series_entry_by_competition
get_user_captained_team_for_scope = legacy.get_user_captained_team_for_scope
get_user_player = legacy.get_user_player
is_admin_user = legacy.is_admin_user
layout = legacy.layout
list_seasons = legacy.list_seasons
load_ai_daily_brief_settings = legacy.load_ai_daily_brief_settings
load_ai_prompt_templates = legacy.load_ai_prompt_templates
load_ai_match_day_report = legacy.load_ai_match_day_report
load_ai_season_summary = legacy.load_ai_season_summary
mask_api_key = legacy.mask_api_key
request_openai_compatible_completion = legacy.request_openai_compatible_completion
render_ai_prompt_template = legacy.render_ai_prompt_template
require_admin = legacy.require_admin
sort_match_days_by_relevance = legacy.sort_match_days_by_relevance
load_season_catalog = legacy.load_season_catalog
load_series_catalog = legacy.load_series_catalog
load_validated_data = legacy.load_validated_data
match_in_scope = legacy.match_in_scope
quote = legacy.quote
redirect = legacy.redirect
resolve_catalog_scope = legacy.resolve_catalog_scope
require_login = legacy.require_login
save_ai_match_day_report = legacy.save_ai_match_day_report
save_ai_season_summary = legacy.save_ai_season_summary
save_season_catalog = legacy.save_season_catalog
season_status_label = legacy.season_status_label
start_response_html = legacy.start_response_html
start_response_json = legacy.start_response_json
team_matches_scope = legacy.team_matches_scope
urlencode = legacy.urlencode


def competition_latest_day_sort_key(row: dict[str, Any]) -> tuple[int, str, str]:
    latest_played_on = str(row.get("latest_played_on") or "").strip()
    try:
        datetime.strptime(latest_played_on, "%Y-%m-%d")
        return (1, latest_played_on, str(row.get("competition_name") or ""))
    except ValueError:
        return (0, "", str(row.get("competition_name") or ""))


def build_group_team_rows(
    data: dict[str, Any],
    competition_name: str,
    season_name: str,
) -> list[dict[str, Any]]:
    played_matches = [
        match
        for match in data["matches"]
        if match_in_scope(match, competition_name, season_name)
        and is_match_counted_as_played(match)
    ]
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    group_rows: dict[tuple[str, str], dict[str, Any]] = {}
    represented_players: dict[tuple[str, str], set[str]] = {}

    for match in played_matches:
        group_label = str(match.get("group_label") or "").strip() or "未分组"
        team_ids_in_match = {
            entry["team_id"]
            for entry in match["players"]
            if entry["team_id"] in team_lookup
        }
        for team_id in team_ids_in_match:
            key = (group_label, team_id)
            if key not in group_rows:
                team = team_lookup[team_id]
                group_rows[key] = {
                    "group_label": group_label,
                    "team_id": team_id,
                    "team_name": team["name"],
                    "matches_represented": 0,
                    "player_count": 0,
                    "points_earned_total": 0.0,
                    "wins": 0,
                }
                represented_players[key] = set()
            group_rows[key]["matches_represented"] += 1

        for entry in match["players"]:
            key = (group_label, entry["team_id"])
            if key not in group_rows:
                continue
            group_rows[key]["points_earned_total"] += float(entry["points_earned"])
            group_rows[key]["wins"] += 1 if entry["result"] == "win" else 0
            represented_players[key].add(entry["player_id"])

    summary: list[dict[str, Any]] = []
    for key, row in group_rows.items():
        row["player_count"] = len(represented_players[key])
        row["points_earned_total"] = round(row["points_earned_total"], 2)
        row["points_per_match"] = (
            round(row["points_earned_total"] / row["matches_represented"], 2)
            if row["matches_represented"]
            else 0.0
        )
        row["win_rate"] = (
            legacy.safe_rate(row["wins"], row["player_count"] and row["matches_represented"] * max(row["player_count"], 1))
            if row["matches_represented"]
            else 0.0
        )
        summary.append(row)

    summary.sort(
        key=lambda item: (
            item.get("stage_label", ""),
            item["group_label"],
            -item["points_earned_total"],
            -item["matches_represented"],
            item["team_name"],
        )
    )
    return summary


def build_stage_group_team_rows(
    data: dict[str, Any],
    competition_name: str,
    season_name: str,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    stage_group_rows: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for stage_key in STAGE_OPTIONS:
        stage_matches = [
            match
            for match in data["matches"]
            if match_in_scope(match, competition_name, season_name)
            and is_match_counted_as_played(match)
            and str(match.get("stage") or "").strip() == stage_key
        ]
        if not stage_matches:
            continue
        stage_data = {
            "teams": data["teams"],
            "players": data["players"],
            "matches": stage_matches,
        }
        grouped_rows = build_group_team_rows(stage_data, competition_name, season_name)
        group_map: dict[str, list[dict[str, Any]]] = {}
        for row in grouped_rows:
            group_map.setdefault(row["group_label"], []).append(row)
        if group_map:
            stage_group_rows[stage_key] = group_map
    return stage_group_rows


def build_stage_team_rows(
    data: dict[str, Any],
    competition_name: str,
    season_name: str,
) -> dict[str, list[dict[str, Any]]]:
    stage_rows: dict[str, list[dict[str, Any]]] = {}
    for stage_key in STAGE_OPTIONS:
        stage_matches = [
            match
            for match in data["matches"]
            if match_in_scope(match, competition_name, season_name)
            and is_match_counted_as_played(match)
            and str(match.get("stage") or "").strip() == stage_key
        ]
        scoped_data = {
            "teams": data["teams"],
            "players": data["players"],
            "matches": stage_matches,
        }
        rows = [
            row
            for row in build_team_rows(scoped_data, competition_name, season_name)
            if row["matches_represented"] > 0
        ]
        rows.sort(
            key=lambda row: (
                row.get("points_rank", 9999),
                -row["points_earned_total"],
                row["name"],
            )
        )
        if rows:
            stage_rows[stage_key] = rows
    return stage_rows


def build_player_mvp_rows(
    data: dict[str, Any],
    competition_name: str,
    season_name: str,
) -> list[dict[str, Any]]:
    played_matches = [
        match
        for match in data["matches"]
        if match_in_scope(match, competition_name, season_name)
        and is_match_counted_as_played(match)
    ]
    player_lookup = {player["player_id"]: player for player in data["players"]}
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    counts: dict[str, dict[str, Any]] = {}
    for match in played_matches:
        mvp_player_id = str(match.get("mvp_player_id") or "").strip()
        if not mvp_player_id or mvp_player_id not in player_lookup:
            continue
        participant = next(
            (entry for entry in match["players"] if entry["player_id"] == mvp_player_id),
            None,
        )
        team_id = str(participant.get("team_id") or "").strip() if participant else ""
        row = counts.setdefault(
            mvp_player_id,
            {
                "player_id": mvp_player_id,
                "display_name": player_lookup[mvp_player_id]["display_name"],
                "team_name": team_lookup.get(team_id, {}).get("name", team_id or "未知战队"),
                "mvp_count": 0,
                "latest_awarded_on": "",
            },
        )
        row["mvp_count"] += 1
        row["latest_awarded_on"] = max(row["latest_awarded_on"], str(match.get("played_on") or ""))

    rows = sorted(counts.values(), key=lambda item: item["display_name"])
    rows.sort(key=lambda item: item["latest_awarded_on"], reverse=True)
    rows.sort(key=lambda item: item["mvp_count"], reverse=True)
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def parse_compact_date(value: str) -> date | None:
    text = str(value or "").strip()
    if len(text) >= 10:
        text = text[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def iter_month_starts(start_day: date, end_day: date) -> list[date]:
    months: list[date] = []
    cursor = date(start_day.year, start_day.month, 1)
    last = date(end_day.year, end_day.month, 1)
    while cursor <= last:
        months.append(cursor)
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return months


def build_season_schedule_calendar(
    matches: list[dict[str, Any]],
    next_path: str,
    season_entry: dict[str, Any] | None = None,
) -> str:
    match_counts_by_day: dict[date, int] = {}
    for match in matches:
        played_day = parse_compact_date(str(match.get("played_on") or ""))
        if played_day is None:
            continue
        match_counts_by_day[played_day] = match_counts_by_day.get(played_day, 0) + 1

    start_day = parse_compact_date(str((season_entry or {}).get("start_at") or ""))
    end_day = parse_compact_date(str((season_entry or {}).get("end_at") or ""))
    scheduled_days = sorted(match_counts_by_day)
    if scheduled_days:
        start_day = start_day or scheduled_days[0]
        end_day = end_day or scheduled_days[-1]
    if start_day is None or end_day is None:
        return '<div class="alert alert-secondary mb-0">当前赛季还没有可展示的比赛日期。</div>'

    if start_day > end_day:
        start_day, end_day = end_day, start_day

    weekday_labels = ["一", "二", "三", "四", "五", "六", "日"]
    month_blocks: list[str] = []
    month_calendar = calendar.Calendar(firstweekday=0)
    for month_start in iter_month_starts(start_day, end_day):
        header_html = "".join(
            f'<div class="schedule-calendar-weekday">{escape(label)}</div>'
            for label in weekday_labels
        )
        day_cells: list[str] = []
        for day in month_calendar.itermonthdates(month_start.year, month_start.month):
            classes = ["schedule-calendar-day"]
            inner_html = f'<span class="schedule-calendar-day-no">{day.day}</span>'
            if day.month != month_start.month:
                classes.append("is-outside")
            else:
                match_count = match_counts_by_day.get(day, 0)
                if match_count > 0:
                    classes.append("has-match")
                    day_path = build_match_day_path(day.isoformat(), next_path)
                    count_text = "1 场" if match_count == 1 else f"{match_count} 场"
                    inner_html = (
                        f'<a class="schedule-calendar-day-link" href="{escape(day_path)}">'
                        f'<span class="schedule-calendar-day-no">{day.day}</span>'
                        f'<span class="schedule-calendar-day-count">{count_text}</span>'
                        f'</a>'
                    )
            day_cells.append(f'<div class="{" ".join(classes)}">{inner_html}</div>')
        month_blocks.append(
            f"""
            <div class="schedule-calendar-month">
              <div class="schedule-calendar-month-title">{month_start.year} 年 {month_start.month} 月</div>
              <div class="schedule-calendar-weekdays">{header_html}</div>
              <div class="schedule-calendar-days">{''.join(day_cells)}</div>
            </div>
            """
        )

    return f'<div class="schedule-calendar-grid">{"".join(month_blocks)}</div>'


def build_match_day_leaderboards(
    data: dict[str, Any],
    played_on: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    completed_matches = [
        match
        for match in data["matches"]
        if str(match.get("played_on") or "").strip() == played_on
        and is_match_counted_as_played(match)
    ]
    stats_data = {
        "teams": data["teams"],
        "players": data["players"],
        "matches": completed_matches,
    }
    player_rows = [row for row in build_player_rows(stats_data) if row["games_played"] > 0]
    team_rows = [
        row
        for row in build_team_rows(stats_data)
        if row["matches_represented"] > 0
    ]
    player_rows.sort(
        key=lambda row: (
            row["rank"],
            -row["points_earned_total"],
            row["display_name"],
        )
    )
    team_rows.sort(
        key=lambda row: (
            row.get("points_rank", 9999),
            -row["points_earned_total"],
            row["name"],
        )
    )
    return completed_matches, player_rows, team_rows


def build_competitions_frontend_page(ctx: RequestContext) -> str:
    if ctx.current_user:
        display_name = ctx.current_user.get("display_name") or ctx.current_user["username"]
        role_label = account_role_label(ctx.current_user)
        account_html = f"""
        <div class="shell-account">
          <span class="shell-account-label">{escape(display_name)} · {escape(role_label)}</span>
          <a class="shell-button shell-button-secondary" href="/profile">控制台</a>
          <form method="post" action="/logout" class="shell-inline-form">
            <button type="submit" class="shell-button shell-button-secondary">退出</button>
          </form>
        </div>
        """
    else:
        account_html = """
        <div class="shell-account">
          <a class="shell-button shell-button-secondary" href="/login">登录</a>
          <a class="shell-button shell-button-primary" href="/register">注册</a>
        </div>
        """

    bootstrap = json.dumps(
        {
            "apiEndpoint": "/api/competitions",
            "alert": form_value(ctx.query, "alert").strip(),
        },
        ensure_ascii=False,
    )
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#f6ece1">
    <title>比赛页面</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/competitions-app.css">
  </head>
  <body class="competitions-app-shell">
    <div class="shell-backdrop"></div>
    <header class="shell-header">
      <div class="shell-brand">
        <a class="shell-brand-link" href="/competitions">比赛页面</a>
        <span class="shell-brand-copy">Events Frontend · API Driven</span>
      </div>
      <nav class="shell-nav" aria-label="主导航">
        <a class="shell-nav-link" href="/dashboard">首页</a>
        <a class="shell-nav-link is-active" href="/competitions">比赛页面</a>
        <a class="shell-nav-link" href="/guilds">门派</a>
      </nav>
      {account_html}
    </header>
    <main id="competitions-app" class="competitions-app-root" aria-live="polite">
      <section class="competitions-loading-shell">
        <div class="competitions-loading-kicker">Loading Events</div>
        <h1>正在加载比赛页面</h1>
        <p>新前端会通过独立 API 拉取地区赛事页和赛季详情。</p>
      </section>
    </main>
    <script>window.__WEREWOLF_COMPETITIONS_BOOTSTRAP__ = {bootstrap};</script>
    <script src="/assets/competitions-app.js" defer></script>
  </body>
</html>
"""


def _build_series_scope(ctx: RequestContext, series_slug: str) -> tuple[dict[str, Any] | None, str]:
    data = load_validated_data()
    catalog = load_series_catalog(data)
    series_entries = get_series_entries_by_slug(catalog, series_slug)
    if not series_entries:
        return None, "没有找到对应的系列赛专题页。"

    competition_rows = build_competition_catalog_rows(data, catalog)
    series_rows = [row for row in competition_rows if row["series_slug"] == series_slug]
    if not series_rows:
        return None, "该系列赛还没有关联任何地区赛事。"

    allowed_competitions = {row["competition_name"] for row in series_rows}
    series_data = build_filtered_data(data, allowed_competitions)
    season_names = list_seasons(series_data, series_slug=series_slug)
    selected_season = get_selected_season(ctx, season_names)
    filtered_matches = [
        match
        for match in sorted(
            series_data["matches"],
            key=lambda item: (
                item["played_on"],
                item["round"],
                item["game_no"],
                item["match_id"],
            ),
            reverse=True,
        )
        if not selected_season or (match.get("season") or "").strip() == selected_season
    ]
    latest_played_on = get_scheduled_match_day_label(
        filtered_matches,
        legacy.china_today_label(),
    )
    region_names = sorted({row["region_name"] for row in series_rows})
    return (
        {
            "data": data,
            "catalog": catalog,
            "series_entries": series_entries,
            "series_rows": series_rows,
            "series_data": series_data,
            "season_names": season_names,
            "selected_season": selected_season,
            "filtered_matches": filtered_matches,
            "latest_played_on": latest_played_on,
            "region_names": region_names,
        },
        "",
    )


def _build_series_legacy_href(series_slug: str, selected_season: str | None) -> str:
    params: dict[str, str] = {}
    if selected_season:
        params["season"] = selected_season
    query = urlencode(params)
    base_path = f"/series/{quote(series_slug)}/legacy"
    return f"{base_path}?{query}" if query else base_path


def _serialize_series_season_links(
    series_slug: str,
    season_names: list[str],
    selected_season: str | None,
) -> list[dict[str, Any]]:
    return [
        {
            "label": season_name,
            "href": build_series_topic_path(series_slug, season_name),
            "selected": selected_season == season_name,
        }
        for season_name in season_names
    ]


def _serialize_series_region_card(
    row: dict[str, Any],
    selected_season: str | None,
) -> dict[str, Any]:
    return {
        "region_name": row["region_name"],
        "competition_name": row["competition_name"],
        "series_name": row["series_name"],
        "seasons": list(row["seasons"]),
        "latest_played_on": row["latest_played_on"] or "待更新",
        "team_count": int(row["team_count"]),
        "player_count": int(row["player_count"]),
        "match_count": int(row["match_count"]),
        "competition_href": build_scoped_path(
            "/competitions",
            row["competition_name"],
            selected_season if selected_season in row["seasons"] else None,
            row["region_name"],
            row["series_slug"],
        ),
    }


def build_series_frontend_page(ctx: RequestContext, series_slug: str) -> str:
    scope, error_message = _build_series_scope(ctx, series_slug)
    if not scope:
        return layout("未找到系列赛", f'<div class="alert alert-danger">{escape(error_message)}</div>', ctx)

    if ctx.current_user:
        display_name = ctx.current_user.get("display_name") or ctx.current_user["username"]
        role_label = account_role_label(ctx.current_user)
        account_html = f"""
        <div class="shell-account">
          <span class="shell-account-label">{escape(display_name)} · {escape(role_label)}</span>
          <a class="shell-button shell-button-secondary" href="/profile">控制台</a>
          <form method="post" action="/logout" class="shell-inline-form">
            <button type="submit" class="shell-button shell-button-secondary">退出</button>
          </form>
        </div>
        """
    else:
        account_html = """
        <div class="shell-account">
          <a class="shell-button shell-button-secondary" href="/login">登录</a>
          <a class="shell-button shell-button-primary" href="/register">注册</a>
        </div>
        """

    bootstrap = json.dumps(
        {
            "apiEndpoint": f"/api/series/{quote(series_slug)}",
            "alert": form_value(ctx.query, "alert").strip(),
        },
        ensure_ascii=False,
    )
    series_name = scope["series_rows"][0]["series_name"]
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#dceef7">
    <title>{escape(series_name)} 专题页</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/competitions-app.css">
  </head>
  <body class="competitions-app-shell">
    <div class="shell-backdrop"></div>
    <header class="shell-header">
      <div class="shell-brand">
        <a class="shell-brand-link" href="{escape(build_series_topic_path(series_slug))}">{escape(series_name)}</a>
        <span class="shell-brand-copy">Series Frontend · API Driven</span>
      </div>
      <nav class="shell-nav" aria-label="主导航">
        <a class="shell-nav-link" href="/dashboard">首页</a>
        <a class="shell-nav-link" href="/competitions">比赛页面</a>
        <a class="shell-nav-link is-active" href="{escape(build_series_topic_path(series_slug))}">系列专题</a>
      </nav>
      {account_html}
    </header>
    <main id="series-app" class="competitions-app-root" aria-live="polite">
      <section class="competitions-loading-shell">
        <div class="competitions-loading-kicker">Loading Series</div>
        <h1>正在加载系列专题页</h1>
        <p>新前端会通过独立 API 拉取赛季入口和地区赛事页概览。</p>
      </section>
    </main>
    <script>window.__WEREWOLF_SERIES_BOOTSTRAP__ = {bootstrap};</script>
    <script src="/assets/series-app.js" defer></script>
  </body>
</html>
"""


def _serialize_filter_links(
    base_path: str,
    region_names: list[str],
    selected_region: str | None,
    series_rows: list[dict[str, Any]],
    selected_series_slug: str | None,
    competition_rows: list[dict[str, Any]],
    selected_competition: str | None,
    season_names: list[str],
    selected_season: str | None,
) -> dict[str, list[dict[str, Any]]]:
    return {
        "regions": [
            {
                "label": region_name,
                "href": build_scoped_path(base_path, None, None, region_name, selected_series_slug),
                "active": selected_region == region_name,
            }
            for region_name in region_names
        ],
        "series": [
            {
                "label": "全部系列赛",
                "href": build_scoped_path(base_path, None, None, selected_region, None),
                "active": selected_series_slug is None,
            }
        ]
        + [
            {
                "label": row["series_name"],
                "href": build_scoped_path(base_path, None, None, selected_region, row["series_slug"]),
                "active": selected_series_slug == row["series_slug"],
            }
            for row in series_rows
        ],
        "competitions": [
            {
                "label": "返回地区赛事列表",
                "href": build_scoped_path(base_path, None, None, selected_region, selected_series_slug),
                "active": selected_competition is None,
            }
        ]
        + [
            {
                "label": row["competition_name"],
                "href": build_scoped_path(
                    base_path,
                    row["competition_name"],
                    None,
                    selected_region,
                    selected_series_slug,
                ),
                "active": selected_competition == row["competition_name"],
            }
            for row in competition_rows
        ],
        "seasons": [
            {
                "label": season_name,
                "href": build_scoped_path(
                    base_path,
                    selected_competition,
                    season_name,
                    selected_region,
                    selected_series_slug,
                ),
                "selected": selected_season == season_name,
            }
            for season_name in season_names
        ],
    }


def _serialize_competition_card(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "competition_name": row["competition_name"],
        "region_name": row["region_name"],
        "series_name": row["series_name"],
        "summary": row["summary"] or f"{row['region_name']}赛区的 {row['series_name']} 赛事页。",
        "seasons": list(row["seasons"]),
        "latest_played_on": row["latest_played_on"] or "待更新",
        "team_count": int(row["team_count"]),
        "player_count": int(row["player_count"]),
        "match_count": int(row["match_count"]),
        "topic_href": build_series_topic_path(row["series_slug"]),
        "competition_href": build_scoped_path(
            "/competitions",
            row["competition_name"],
            None,
            row["region_name"],
            row["series_slug"],
        ),
    }


def _serialize_team_ranking_row(
    row: dict[str, Any],
    competition_name: str | None,
    season_name: str | None,
    region_name: str | None,
    series_slug: str | None,
) -> dict[str, Any]:
    return {
        "rank": int(row.get("points_rank", row.get("rank", 0))),
        "team_id": row["team_id"],
        "name": row["name"],
        "player_count": int(row["player_count"]),
        "matches_represented": int(row["matches_represented"]),
        "points_total": f'{float(row["points_earned_total"]):.2f}',
        "points_per_match": f'{float(row.get("points_per_match", 0.0)):.2f}',
        "win_rate": format_pct(float(row["win_rate"])),
        "href": build_scoped_path(
            "/teams/" + row["team_id"],
            competition_name,
            season_name,
            region_name,
            series_slug,
        ),
    }


def _serialize_player_ranking_row(
    row: dict[str, Any],
    competition_name: str | None,
    season_name: str | None,
    region_name: str | None,
    series_slug: str | None,
) -> dict[str, Any]:
    return {
        "rank": int(row["rank"]),
        "player_id": row["player_id"],
        "display_name": row["display_name"],
        "team_name": row["team_name"],
        "games_played": int(row["games_played"]),
        "record": row["record"],
        "points_total": f'{float(row["points_earned_total"]):.2f}',
        "average_points": f'{float(row["average_points"]):.2f}',
        "win_rate": format_pct(float(row["win_rate"])),
        "href": build_scoped_path(
            "/players/" + row["player_id"],
            competition_name,
            season_name,
            region_name,
            series_slug,
        ),
    }


def build_competitions_api_payload(ctx: RequestContext) -> dict[str, Any]:
    data = load_validated_data()
    scope = resolve_catalog_scope(ctx, data)
    competition_rows = scope["competition_rows"]
    selected_competition = scope["selected_competition"]
    selected_entry = scope["selected_entry"]
    selected_region = scope["selected_region"]
    selected_series_slug = scope["selected_series_slug"]
    region_rows = scope["region_rows"]
    filtered_rows = scope["filtered_rows"]
    series_rows = scope["series_rows"]
    season_catalog = load_season_catalog(data)
    season_names = list_seasons(data, selected_competition) if selected_competition else []
    selected_season = get_selected_season(ctx, season_names)
    visible_competitions = filtered_rows or region_rows
    legacy_href = build_scoped_path(
        "/competitions/legacy",
        selected_competition,
        selected_season,
        selected_region,
        selected_series_slug,
    )
    filters = _serialize_filter_links(
        "/competitions",
        scope["region_names"],
        selected_region,
        series_rows,
        selected_series_slug,
        filtered_rows or region_rows or competition_rows,
        selected_competition,
        season_names,
        selected_season,
    )

    if not selected_competition:
        featured_competition = max(
            visible_competitions or competition_rows,
            key=competition_latest_day_sort_key,
            default=None,
        )
        total_match_count = sum(row["match_count"] for row in visible_competitions)
        total_team_count = max((row["team_count"] for row in visible_competitions), default=0)
        cards = [_serialize_competition_card(row) for row in visible_competitions]
        return {
            "view": "list",
            "generated_at": ctx.now_label,
            "legacy_href": legacy_href,
            "scope": {
                "selected_region": selected_region,
                "selected_series_slug": selected_series_slug,
                "filters": {
                    "regions": filters["regions"],
                    "series": filters["series"],
                },
            },
            "hero": {
                "title": f"{selected_region or DEFAULT_REGION_NAME}赛区入口",
                "copy": "先选择地区，再筛选系列赛。每张卡片都同时提供系列赛专题页和该地区的独立赛事站点，方便按赛区管理和按品牌汇总浏览。",
                "featured_name": featured_competition["competition_name"] if featured_competition else "等待录入赛事",
                "featured_latest": featured_competition["latest_played_on"] if featured_competition else "待更新",
                "featured_seasons": (
                    " / ".join(featured_competition["seasons"][:2])
                    if featured_competition and featured_competition["seasons"]
                    else "赛季待录入"
                ),
            },
            "metrics": [
                {
                    "label": "地区站点",
                    "value": str(len(visible_competitions)),
                    "copy": f"{selected_region or DEFAULT_REGION_NAME} 当前可见",
                },
                {
                    "label": "覆盖战队",
                    "value": str(total_team_count),
                    "copy": "当前地区口径",
                },
                {
                    "label": "累计对局",
                    "value": str(total_match_count),
                    "copy": "当前筛选下完整赛程",
                },
            ],
            "management": {
                "can_manage_series": can_access_series_management(ctx.current_user),
                "manage_href": "/series-manage",
            },
            "cards": cards,
        }

    competition_meta = selected_entry
    played_match_rows = [
        match
        for match in data["matches"]
        if match_in_scope(match, selected_competition, selected_season)
        and is_match_counted_as_played(match)
    ]
    stats_data = {
        "teams": data["teams"],
        "players": data["players"],
        "matches": played_match_rows,
    }
    team_rows = [
        row
        for row in build_team_rows(stats_data, selected_competition, selected_season)
        if row["matches_represented"] > 0
    ]
    player_rows = [
        row
        for row in build_player_rows(stats_data, selected_competition, selected_season)
        if row["games_played"] > 0
    ]
    stage_team_rows = build_stage_team_rows(data, selected_competition, selected_season or "")
    stage_group_team_rows = build_stage_group_team_rows(data, selected_competition, selected_season or "")
    mvp_rows = build_player_mvp_rows(data, selected_competition, selected_season or "")
    team_rows.sort(key=lambda row: (row.get("points_rank", 9999), -row["points_earned_total"], row["name"]))
    player_rows.sort(key=lambda row: (row["rank"], -row["points_earned_total"], row["display_name"]))
    match_rows = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
        )
        if match_in_scope(match, selected_competition, selected_season)
    ]
    player_count = len({entry["player_id"] for match in match_rows for entry in match["players"]})
    scope_label = " / ".join(item for item in [selected_competition, selected_season] if item) or "比赛总览"
    current_competition_path = build_scoped_path(
        "/competitions",
        selected_competition,
        selected_season,
        selected_region,
        selected_series_slug,
    )
    can_manage_selected_match_scope = bool(
        selected_competition and can_manage_matches(ctx.current_user, data, selected_competition)
    )
    can_edit_selected_competition = bool(
        selected_competition and can_manage_competition_catalog(ctx.current_user, data, selected_competition)
    )
    can_manage_selected_seasons = bool(
        selected_competition and can_manage_competition_seasons(ctx.current_user, data, selected_competition)
    )
    season_entry = (
        get_season_entry(
            season_catalog,
            selected_series_slug,
            selected_season,
            competition_name=selected_competition,
        )
        if selected_series_slug and selected_season
        else None
    )
    page_badge = (
        competition_meta["page_badge"]
        if competition_meta and competition_meta.get("page_badge")
        else f"{competition_meta['region_name'] if competition_meta else selected_region or DEFAULT_REGION_NAME} · 赛事专属页面"
    )
    hero_title = (
        competition_meta["hero_title"]
        if competition_meta and competition_meta.get("hero_title")
        else selected_competition
    )
    hero_intro = (
        competition_meta["hero_intro"]
        if competition_meta and competition_meta.get("hero_intro")
        else "当前页面只展示这个地区赛事站点下指定赛季的战队、队员和对局。你可以先切换地区与系列赛，再切换赛季，然后继续进入战队详情页查看更深一层的数据。"
    )
    hero_note = (
        competition_meta["hero_note"]
        if competition_meta and competition_meta.get("hero_note")
        else f"这里会保留 {competition_meta['series_name'] if competition_meta else selected_competition} 在 {competition_meta['region_name'] if competition_meta else selected_region or DEFAULT_REGION_NAME} 赛区当前赛季独立的排名和赛程视角。"
    )
    latest_played_on = get_scheduled_match_day_label(match_rows, legacy.china_today_label())
    season_status_text = "待配置"
    season_period_text = "请先设置赛季起止时间"
    season_note_text = "当前赛季还没有配置档期。"
    if season_entry:
        season_status_text = season_status_label(season_entry)
        season_period_text = (
            f"{format_datetime_local_label(season_entry.get('start_at', ''))} - "
            f"{format_datetime_local_label(season_entry.get('end_at', ''))}"
        )
        season_note_text = season_entry.get("notes") or "这里展示当前赛季的进行状态、档期与补充说明。"

    ai_season_summary = (
        load_ai_season_summary(selected_competition, selected_season)
        if selected_competition and selected_season
        else None
    )
    ai_settings = load_ai_daily_brief_settings()
    ai_configured = bool(ai_settings.get("base_url") and ai_settings.get("api_key"))

    grouped_team_boards = []
    for stage_key, groups in stage_group_team_rows.items():
        grouped_team_boards.append(
            {
                "stage_key": stage_key,
                "stage_label": STAGE_OPTIONS.get(stage_key, stage_key),
                "groups": [
                    {
                        "group_label": group_label,
                        "rows": [
                            {
                                "rank": index + 1,
                                "team_id": row["team_id"],
                                "name": row["team_name"],
                                "matches_represented": int(row["matches_represented"]),
                                "player_count": int(row["player_count"]),
                                "points_total": f'{float(row["points_earned_total"]):.2f}',
                                "points_per_match": f'{float(row["points_per_match"]):.2f}',
                                "win_rate": format_pct(float(row.get("win_rate", 0.0))),
                                "href": build_scoped_path(
                                    "/teams/" + row["team_id"],
                                    selected_competition,
                                    selected_season,
                                    selected_region,
                                    selected_series_slug,
                                ),
                            }
                            for index, row in enumerate(rows)
                        ],
                    }
                    for group_label, rows in groups.items()
                ],
            }
        )

    season_match_days: list[dict[str, Any]] = []
    seen_days: list[str] = []
    for match in match_rows:
        played_on = str(match.get("played_on") or "").strip()
        if played_on and played_on not in seen_days:
            seen_days.append(played_on)
    for played_on in seen_days:
        season_match_days.append(
            {
                "played_on": played_on,
                "match_count": sum(
                    1 for match in match_rows if str(match.get("played_on") or "").strip() == played_on
                ),
                "href": build_match_day_path(played_on, current_competition_path),
            }
        )

    ai_payload = {
        "configured": ai_configured,
        "summary": None,
        "generate_form": None,
        "edit_form": None,
        "settings_href": "/accounts",
    }
    if ai_season_summary:
        ai_payload["summary"] = {
            "generated_at": ai_season_summary.get("generated_at") or "未生成",
            "model": ai_season_summary.get("model") or ai_settings.get("model") or legacy.DEFAULT_AI_DAILY_BRIEF_MODEL,
            "html": render_ai_daily_brief_html(ai_season_summary.get("content") or ""),
        }
    if selected_competition and selected_season and ai_configured and (
        not ai_season_summary or is_admin_user(ctx.current_user)
    ):
        ai_payload["generate_form"] = {
            "button_label": "重生成 AI 赛季总结" if ai_season_summary else "生成 AI 赛季总结",
            "fields": {
                "action": "generate_ai_season_summary",
                "competition_name": selected_competition,
                "season_name": selected_season,
                "region_name": selected_region or "",
                "series_slug": selected_series_slug or "",
            },
        }
    if (
        selected_competition
        and selected_season
        and is_admin_user(ctx.current_user)
        and ai_season_summary
    ):
        ai_payload["edit_form"] = {
            "fields": {
                "action": "save_ai_season_summary",
                "competition_name": selected_competition,
                "season_name": selected_season,
                "region_name": selected_region or "",
                "series_slug": selected_series_slug or "",
            },
            "content": ai_season_summary.get("content") or "",
        }

    return {
        "view": "detail",
        "generated_at": ctx.now_label,
        "legacy_href": legacy_href,
        "scope": {
            "label": scope_label,
            "selected_region": selected_region,
            "selected_series_slug": selected_series_slug,
            "selected_competition": selected_competition,
            "selected_season": selected_season,
            "filters": filters,
        },
        "hero": {
            "badge": page_badge,
            "title": hero_title,
            "intro": hero_intro,
            "note": hero_note,
            "latest_played_on": latest_played_on or "待更新",
            "latest_seasons": (
                selected_season
                or (
                    " / ".join(competition_meta["seasons"][:2])
                    if competition_meta and competition_meta["seasons"]
                    else "赛季待录入"
                )
            ),
        },
        "metrics": [
            {
                "label": "参赛战队",
                "value": str(len(team_rows)),
                "copy": f"{selected_season or '当前赛季'} 真实参赛",
            },
            {
                "label": "参赛队员",
                "value": str(player_count),
                "copy": f"{selected_season or '当前赛季'} 已上场",
            },
            {
                "label": "赛季场次",
                "value": str(len(match_rows)),
                "copy": f"{scope_label} 完整赛程",
            },
        ],
        "actions": {
            "create_match_href": (
                "/matches/new?"
                + urlencode(
                    {
                        "competition": selected_competition,
                        "season": selected_season or "",
                        "next": current_competition_path,
                    }
                )
                if can_manage_selected_match_scope
                else ""
            ),
            "edit_competition_href": (
                build_series_manage_path(selected_competition, current_competition_path, None, "catalog")
                if can_edit_selected_competition
                else ""
            ),
            "series_topic_href": (
                build_series_topic_path(competition_meta["series_slug"], selected_season)
                if competition_meta
                else ""
            ),
            "schedule_href": build_schedule_path(
                selected_competition,
                selected_season,
                current_competition_path,
                selected_region,
                selected_series_slug,
            ),
            "back_href": build_scoped_path("/competitions", None, None, selected_region, selected_series_slug),
            "season_manage_href": (
                build_series_manage_path(selected_competition, current_competition_path, selected_season, "season")
                if can_manage_selected_seasons
                else ""
            ),
        },
        "season_info": {
            "name": selected_season,
            "status": season_status_text,
            "period": season_period_text,
            "note": season_note_text,
        },
        "ai": ai_payload,
        "leaderboards": {
            "stage_team": [
                {
                    "stage_key": stage_key,
                    "stage_label": STAGE_OPTIONS.get(stage_key, stage_key),
                    "rows": [
                        _serialize_team_ranking_row(
                            row,
                            selected_competition,
                            selected_season,
                            selected_region,
                            selected_series_slug,
                        )
                        for row in rows
                    ],
                }
                for stage_key, rows in stage_team_rows.items()
            ],
            "group_team": grouped_team_boards,
            "players": [
                _serialize_player_ranking_row(
                    row,
                    selected_competition,
                    selected_season,
                    selected_region,
                    selected_series_slug,
                )
                for row in player_rows
            ],
            "mvp": [
                {
                    "rank": int(row["rank"]),
                    "player_id": row["player_id"],
                    "display_name": row["display_name"],
                    "team_name": row["team_name"],
                    "mvp_count": int(row["mvp_count"]),
                    "latest_awarded_on": row.get("latest_awarded_on") or "待更新",
                    "href": build_scoped_path(
                        "/players/" + row["player_id"],
                        selected_competition,
                        selected_season,
                        selected_region,
                        selected_series_slug,
                    ),
                }
                for row in mvp_rows
            ],
        },
        "teams": [
            {
                "team_id": row["team_id"],
                "name": row["name"],
                "href": build_scoped_path(
                    "/teams/" + row["team_id"],
                    selected_competition,
                    selected_season,
                    selected_region,
                    selected_series_slug,
                ),
            }
            for row in team_rows
        ],
        "match_days": season_match_days,
    }


def handle_competitions_api(ctx: RequestContext, start_response):
    if ctx.method != "GET":
        return start_response_json(
            start_response,
            "405 Method Not Allowed",
            {"error": "competitions api only supports GET"},
            headers=[("Allow", "GET")],
        )
    return start_response_json(
        start_response,
        "200 OK",
        build_competitions_api_payload(ctx),
    )


def get_competitions_page(ctx: RequestContext, alert: str = "") -> str:
    data = load_validated_data()
    scope = resolve_catalog_scope(ctx, data)
    competition_rows = scope["competition_rows"]
    selected_competition = scope["selected_competition"]
    selected_entry = scope["selected_entry"]
    selected_region = scope["selected_region"]
    selected_series_slug = scope["selected_series_slug"]
    region_rows = scope["region_rows"]
    filtered_rows = scope["filtered_rows"]
    series_rows = scope["series_rows"]
    season_catalog = load_season_catalog(data)
    season_names = list_seasons(data, selected_competition) if selected_competition else []
    selected_season = get_selected_season(ctx, season_names)
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    featured_competition = max(
        filtered_rows or region_rows or competition_rows,
        key=competition_latest_day_sort_key,
        default=None,
    )
    region_switcher = build_region_switcher("/competitions", scope["region_names"], selected_region, selected_series_slug)
    series_switcher = build_series_switcher("/competitions", series_rows, selected_region, selected_series_slug)

    if not selected_competition:
        cards = []
        for row in filtered_rows or region_rows:
            topic_path = build_series_topic_path(row["series_slug"])
            competition_path = build_scoped_path("/competitions", row["competition_name"], None, row["region_name"], row["series_slug"])
            card_summary = row["summary"] or f"{row['region_name']}赛区的 {row['series_name']} 赛事页。"
            cards.append(
                f"""
                <div class="col-12 col-lg-6">
                  <div class="team-link-card shadow-sm p-4 h-100">
                    <div class="d-flex justify-content-between align-items-start gap-3">
                      <div>
                        <div class="card-kicker mb-2">{escape(row['region_name'])} · {escape(row['series_name'])}</div>
                        <h2 class="h4 mb-2">{escape(row['competition_name'])}</h2>
                        <div class="small-muted mb-2">赛季 {escape('、'.join(row['seasons'])) if row['seasons'] else '待录入'}</div>
                        <div class="small-muted mb-3">最近比赛日 {f'<span>{escape(row["latest_played_on"])}</span>' if row['latest_played_on'] else '待更新'}</div>
                        <p class="section-copy mb-0">{escape(card_summary)}</p>
                      </div>
                      <span class="chip">专题 + 地区站点</span>
                    </div>
                    <div class="row g-3">
                      <div class="col-4"><div class="small text-secondary">战队</div><div class="fw-semibold">{row['team_count']} 支</div></div>
                      <div class="col-4"><div class="small text-secondary">队员</div><div class="fw-semibold">{row['player_count']} 名</div></div>
                      <div class="col-4"><div class="small text-secondary">对局</div><div class="fw-semibold">{row['match_count']} 场</div></div>
                    </div>
                    <div class="d-flex flex-wrap gap-2 mt-4">
                      <a class="btn btn-dark" href="{escape(topic_path)}">查看系列专题</a>
                      <a class="btn btn-outline-dark" href="{escape(competition_path)}">进入地区赛事页</a>
                    </div>
                  </div>
                </div>
                """
            )
        total_match_count = sum(row["match_count"] for row in (filtered_rows or region_rows))
        total_team_count = max((row["team_count"] for row in (filtered_rows or region_rows)), default=0)
        featured_name = featured_competition["competition_name"] if featured_competition else "等待录入赛事"
        featured_latest = featured_competition["latest_played_on"] if featured_competition else "待更新"
        featured_seasons = (
            " / ".join(featured_competition["seasons"][:2]) if featured_competition and featured_competition["seasons"] else "赛季待录入"
        )
        manage_button = '<a class="btn btn-dark" href="/series-manage">创建或维护系列赛</a>' if can_access_series_management(ctx.current_user) else ""
        body = f"""
        <section class="hero p-4 p-md-5 shadow-lg mb-4"><div class="hero-layout"><div><div class="eyebrow mb-3">地区赛事站点</div><h1 class="hero-title mb-3">{escape(selected_region or DEFAULT_REGION_NAME)}赛区入口</h1><p class="hero-copy mb-0">先选择地区，再筛选系列赛。每张卡片都同时提供系列赛专题页和该地区的独立赛事站点，方便按赛区管理和按品牌汇总浏览。</p><div class="hero-switchers mt-4">{region_switcher}</div><div class="hero-switchers mt-3">{series_switcher}</div><div class="hero-kpis"><div class="hero-pill"><span>地区站点</span><strong>{len(filtered_rows or region_rows)}</strong><small>{escape(selected_region or DEFAULT_REGION_NAME)} 当前可见</small></div><div class="hero-pill"><span>覆盖战队</span><strong>{total_team_count}</strong><small>当前地区口径</small></div><div class="hero-pill"><span>累计对局</span><strong>{total_match_count}</strong><small>当前筛选下完整赛程</small></div></div></div><div class="hero-stage-card"><div class="official-mark">Event Portal</div><div class="hero-stage-label">Featured Regional Event</div><div class="hero-stage-title">{escape(featured_name)}</div><div class="hero-stage-note">未登录时首页默认展示广州赛区；登录后会优先按账号所在地区进入对应赛区。进入单个地区赛事页后，你会继续看到该站自己的战队入口、赛程表和赛季切换，不会和其他地区混排。</div><div class="hero-stage-grid"><div class="hero-stage-metric"><span>最近比赛日</span><strong>{escape(featured_latest)}</strong><small>{escape(featured_seasons)}</small></div><div class="hero-stage-metric"><span>参赛战队</span><strong>{featured_competition['team_count'] if featured_competition else 0}</strong><small>当前特色赛事</small></div><div class="hero-stage-metric"><span>参赛队员</span><strong>{featured_competition['player_count'] if featured_competition else 0}</strong><small>当前特色赛事</small></div><div class="hero-stage-metric"><span>赛事场次</span><strong>{featured_competition['match_count'] if featured_competition else 0}</strong><small>当前特色地区站点</small></div></div></div></div></section>
        <section class="panel shadow-sm p-3 p-lg-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-4"><div><h2 class="section-title mb-2">该地区系列赛站点</h2><p class="section-copy mb-0">同一系列赛可以进入专题页查看跨地区汇总，也可以单独进入当前地区赛事页查看该站独立赛季。</p></div><div class="d-flex flex-wrap gap-2">{manage_button}</div></div><div class="row g-3 g-lg-4">{''.join(cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">当前地区还没有系列赛站点，请先创建系列赛。</div></div>'}</div></section>
        """
        return layout("比赛页面", body, ctx, alert=alert)

    competition_switcher = build_competition_switcher("/competitions", [row["competition_name"] for row in (filtered_rows or region_rows or competition_rows)], selected_competition, tone="light", all_label="返回地区赛事列表", region_name=selected_region, series_slug=selected_series_slug)
    season_switcher = build_season_switcher("/competitions", selected_competition, season_names, selected_season, tone="light", region_name=selected_region, series_slug=selected_series_slug)
    competition_meta = selected_entry
    can_manage_selected_match_scope = bool(selected_competition and can_manage_matches(ctx.current_user, data, selected_competition))
    can_edit_selected_competition = bool(selected_competition and can_manage_competition_catalog(ctx.current_user, data, selected_competition))
    can_manage_selected_seasons = bool(selected_competition and can_manage_competition_seasons(ctx.current_user, data, selected_competition))
    season_entry = get_season_entry(season_catalog, selected_series_slug, selected_season, competition_name=selected_competition) if selected_series_slug and selected_season else None
    played_match_rows = [
        match
        for match in data["matches"]
        if match_in_scope(match, selected_competition, selected_season)
        and is_match_counted_as_played(match)
    ]
    stats_data = {
        "teams": data["teams"],
        "players": data["players"],
        "matches": played_match_rows,
    }
    team_rows = [row for row in build_team_rows(stats_data, selected_competition, selected_season) if row["matches_represented"] > 0]
    player_rows = [row for row in build_player_rows(stats_data, selected_competition, selected_season) if row["games_played"] > 0]
    stage_team_rows = build_stage_team_rows(data, selected_competition, selected_season or "")
    stage_group_team_rows = build_stage_group_team_rows(data, selected_competition, selected_season or "")
    mvp_rows = build_player_mvp_rows(data, selected_competition, selected_season or "")
    team_rows.sort(key=lambda row: (row.get("points_rank", 9999), -row["points_earned_total"], row["name"]))
    player_rows.sort(key=lambda row: (row["rank"], -row["points_earned_total"], row["display_name"]))
    match_rows = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
        )
        if match_in_scope(match, selected_competition, selected_season)
    ]
    player_count = len({entry["player_id"] for match in match_rows for entry in match["players"]})
    scope_label = " / ".join(item for item in [selected_competition, selected_season] if item) or "比赛总览"
    season_switcher_html = f'<div class="hero-switchers mt-3">{season_switcher}</div>' if season_switcher else ""
    region_switcher_html = f'<div class="hero-switchers mt-4">{region_switcher}</div>' if region_switcher else ""
    series_switcher_html = f'<div class="hero-switchers mt-3">{series_switcher}</div>' if series_switcher else ""
    current_competition_path = build_scoped_path("/competitions", selected_competition, selected_season, selected_region, selected_series_slug)
    page_badge = competition_meta["page_badge"] if competition_meta and competition_meta.get("page_badge") else f"{competition_meta['region_name'] if competition_meta else selected_region or DEFAULT_REGION_NAME} · 赛事专属页面"
    hero_title = competition_meta["hero_title"] if competition_meta and competition_meta.get("hero_title") else selected_competition
    hero_intro = competition_meta["hero_intro"] if competition_meta and competition_meta.get("hero_intro") else "当前页面只展示这个地区赛事站点下指定赛季的战队、队员和对局。你可以先切换地区与系列赛，再切换赛季，然后继续进入战队详情页查看更深一层的数据。"
    hero_note = competition_meta["hero_note"] if competition_meta and competition_meta.get("hero_note") else f"这里会保留 {competition_meta['series_name'] if competition_meta else selected_competition} 在 {competition_meta['region_name'] if competition_meta else selected_region or DEFAULT_REGION_NAME} 赛区当前赛季独立的排名和赛程视角。"
    create_match_button = f'<a class="btn btn-dark" href="/matches/new?{urlencode({"competition": selected_competition, "season": selected_season or "", "next": current_competition_path})}">创建或导入比赛</a>' if can_manage_selected_match_scope else ""
    schedule_page_button = f'<a class="btn btn-outline-dark" href="{escape(build_schedule_path(selected_competition, selected_season, current_competition_path, selected_region, selected_series_slug))}">查看全部场次</a>'
    series_topic_button = f'<a class="btn btn-outline-dark" href="{escape(build_series_topic_path(competition_meta["series_slug"], selected_season))}">查看系列专题页</a>' if competition_meta else ""
    edit_competition_button = f'<a class="btn btn-outline-dark" href="{escape(build_series_manage_path(selected_competition, current_competition_path, None, "catalog"))}">编辑赛事页信息</a>' if can_edit_selected_competition else ""
    season_manage_button = f'<a class="btn btn-outline-dark" href="{escape(build_series_manage_path(selected_competition, current_competition_path, selected_season, "season"))}">管理赛季档期</a>' if can_manage_selected_seasons else ""
    latest_played_on = get_scheduled_match_day_label(
        match_rows,
        legacy.china_today_label(),
    )
    season_status_text = "待配置"
    season_period_text = "请先设置赛季起止时间"
    season_note_text = "当前赛季还没有配置档期。"
    if season_entry:
        season_status_text = season_status_label(season_entry)
        season_period_text = f"{format_datetime_local_label(season_entry.get('start_at', ''))} - {format_datetime_local_label(season_entry.get('end_at', ''))}"
        season_note_text = season_entry.get("notes") or "这里展示当前赛季的进行状态、档期与补充说明。"
    season_registration_panel = ""
    if selected_season:
        season_registration_panel = f"""<section class="panel shadow-sm p-3 p-lg-4 mb-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h2 class="section-title mb-2">赛季档期</h2><p class="section-copy mb-0">当前查看的是 {escape(selected_season)}。赛季战队与队员由比赛补录、战队档案和管理员维护直接决定，不再单独提供报名操作。</p></div><div class="d-flex flex-wrap gap-2">{season_manage_button}</div></div><div class="team-link-card shadow-sm p-4"><div class="card-kicker mb-2">赛季状态</div><h3 class="h5 mb-2">{escape(season_status_text)}</h3><div class="small-muted mb-2">起止时间 {escape(season_period_text)}</div><p class="section-copy mb-0">{escape(season_note_text)}</p></div></section>"""
    stage_team_sections: list[str] = []
    for stage_key, rows in stage_team_rows.items():
        stage_table_rows = "".join(
            f"""<tr><td>{row.get('points_rank', '-')}</td><td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(build_scoped_path('/teams/' + row['team_id'], selected_competition, selected_season, selected_region, selected_series_slug))}">{escape(row['name'])}</a></td><td>{row['matches_represented']}</td><td>{row['player_count']}</td><td>{row['points_earned_total']:.2f}</td><td>{row.get('points_per_match', 0.0):.2f}</td><td>{format_pct(row['win_rate'])}</td></tr>"""
            for row in rows
        )
        stage_team_sections.append(
            f"""<div class="col-12 col-xxl-6"><div class="panel h-100 shadow-sm p-3"><h3 class="h5 mb-3">{escape(STAGE_OPTIONS.get(stage_key, stage_key))}</h3><div class="table-responsive"><table class="table align-middle mb-0"><thead><tr><th>排名</th><th>战队</th><th>场次</th><th>上场队员</th><th>总积分</th><th>场均积分</th><th>胜率</th></tr></thead><tbody>{stage_table_rows}</tbody></table></div></div></div>"""
        )
    grouped_team_sections: list[str] = []
    for stage_key, group_map in stage_group_team_rows.items():
        stage_group_blocks: list[str] = []
        for group_label, rows in group_map.items():
            group_table_rows = "".join(
                f"""<tr><td>{index}</td><td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(build_scoped_path('/teams/' + row['team_id'], selected_competition, selected_season, selected_region, selected_series_slug))}">{escape(row['team_name'])}</a></td><td>{row['matches_represented']}</td><td>{row['player_count']}</td><td>{row['points_earned_total']:.2f}</td><td>{row['points_per_match']:.2f}</td></tr>"""
                for index, row in enumerate(rows, start=1)
            )
            stage_group_blocks.append(
                f"""<div class="col-12 col-xxl-6"><div class="panel h-100 shadow-sm p-3"><h4 class="h6 mb-3">{escape(group_label)}</h4><div class="table-responsive"><table class="table align-middle mb-0"><thead><tr><th>排名</th><th>战队</th><th>场次</th><th>上场队员</th><th>总积分</th><th>场均积分</th></tr></thead><tbody>{group_table_rows or '<tr><td colspan="6" class="text-secondary">当前分组还没有积分数据。</td></tr>'}</tbody></table></div></div></div>"""
            )
        grouped_team_sections.append(
            f"""<section class="panel shadow-sm p-3 p-lg-4 mb-3"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h3 class="h5 mb-2">{escape(STAGE_OPTIONS.get(stage_key, stage_key))}</h3><p class="section-copy mb-0">该赛段内再按比赛实际录入的分组拆分统计战队积分。</p></div></div><div class="row g-3">{''.join(stage_group_blocks)}</div></section>"""
        )
    player_points_rows = [f"""<tr><td>{row['rank']}</td><td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(build_scoped_path('/players/' + row['player_id'], selected_competition, selected_season, selected_region, selected_series_slug))}">{escape(row['display_name'])}</a></td><td>{escape(row['team_name'])}</td><td>{row['games_played']}</td><td>{escape(row['record'])}</td><td>{row['points_earned_total']:.2f}</td><td>{row['average_points']:.2f}</td><td>{format_pct(row['win_rate'])}</td></tr>""" for row in player_rows]
    mvp_table_rows = "".join(
        f"""<tr><td>{row['rank']}</td><td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(build_scoped_path('/players/' + row['player_id'], selected_competition, selected_season, selected_region, selected_series_slug))}">{escape(row['display_name'])}</a></td><td>{escape(row['team_name'])}</td><td>{row['mvp_count']}</td><td>{escape(row['latest_awarded_on'] or '待更新')}</td></tr>"""
        for row in mvp_rows
    )
    leaderboard_sections = f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">积分榜</h2>
          <p class="section-copy mb-0">默认先展示战队积分榜；如需查看分组战队榜、个人积分榜或个人 MVP 榜，可通过下拉菜单自由切换。</p>
        </div>
        <div style="min-width: 240px;">
          <label class="form-label mb-2" for="season-leaderboard-select">选择榜单</label>
          <select class="form-select" id="season-leaderboard-select" data-season-leaderboard-select>
            <option value="team" selected>战队积分榜</option>
            <option value="group-team">分组战队积分榜</option>
            <option value="player">个人积分榜</option>
            <option value="mvp">个人 MVP 榜</option>
          </select>
        </div>
      </div>
      <div data-season-leaderboard-panel="team">
        <div class="mb-3">
          <h3 class="h5 mb-2">战队积分榜</h3>
          <p class="section-copy mb-0">战队积分按赛段分别统计。每个赛段只累计该赛段下已录入完成比赛的战队总积分。</p>
        </div>
        <div class="row g-3">{''.join(stage_team_sections) or '<div class="col-12"><div class="alert alert-secondary mb-0">当前赛季还没有可统计的赛段战队积分数据。</div></div>'}</div>
      </div>
      <div data-season-leaderboard-panel="group-team" hidden>
        <div class="mb-3">
          <h3 class="h5 mb-2">分组战队积分榜</h3>
          <p class="section-copy mb-0">分组战队积分榜同样按赛段统计，因为不同赛段的战队分组可能不同。每个赛段内再按比赛实际录入的分组分别展示。</p>
        </div>
        {''.join(grouped_team_sections) or '<div class="alert alert-secondary mb-0">当前赛季还没有可统计的分组战队积分数据。</div>'}
      </div>
      <div data-season-leaderboard-panel="player" hidden>
        <div class="mb-3">
          <h3 class="h5 mb-2">个人积分榜</h3>
          <p class="section-copy mb-0">个人积分榜按当前赛事与赛季下全部已录入完成的比赛累计，不再按赛段拆分，方便直接看整个赛季的个人表现。</p>
        </div>
        <div class="table-responsive"><table class="table align-middle"><thead><tr><th>排名</th><th>选手</th><th>战队</th><th>出场</th><th>战绩</th><th>赛季总积分</th><th>场均得分</th><th>胜率</th></tr></thead><tbody>{''.join(player_points_rows) or '<tr><td colspan="8" class="text-secondary">当前赛季还没有选手积分数据。</td></tr>'}</tbody></table></div>
      </div>
      <div data-season-leaderboard-panel="mvp" hidden>
        <div class="mb-3">
          <h3 class="h5 mb-2">个人 MVP 榜</h3>
          <p class="section-copy mb-0">按当前赛事与赛季下全部已录入完成的比赛累计 MVP 次数。若同次数，则最近获奖日期更晚的选手排在前面。</p>
        </div>
        <div class="table-responsive"><table class="table align-middle"><thead><tr><th>排名</th><th>选手</th><th>战队</th><th>MVP 次数</th><th>最近获奖</th></tr></thead><tbody>{mvp_table_rows or '<tr><td colspan="5" class="text-secondary">当前赛季还没有 MVP 数据。</td></tr>'}</tbody></table></div>
      </div>
      <script>
        (() => {{
          const select = document.querySelector("[data-season-leaderboard-select]");
          if (!select) return;
          const panels = Array.from(document.querySelectorAll("[data-season-leaderboard-panel]"));
          const syncPanels = () => {{
            const selectedValue = select.value;
            panels.forEach((panel) => {{
              panel.hidden = panel.getAttribute("data-season-leaderboard-panel") !== selectedValue;
            }});
          }};
          select.addEventListener("change", syncPanels);
          syncPanels();
        }})();
      </script>
    </section>
    """
    team_links_html = "".join(
        f"""<a class="switcher-chip" href="{escape(build_scoped_path('/teams/' + row['team_id'], selected_competition, selected_season, selected_region, selected_series_slug))}">{escape(row['name'])}</a>"""
        for row in team_rows
    )
    season_schedule_calendar = build_season_schedule_calendar(
        match_rows,
        build_scoped_path("/competitions", selected_competition, selected_season, selected_region, selected_series_slug),
        season_entry,
    )
    ai_season_summary = (
        load_ai_season_summary(selected_competition, selected_season)
        if selected_competition and selected_season
        else None
    )
    ai_settings = load_ai_daily_brief_settings()
    ai_configured = bool(ai_settings.get("base_url") and ai_settings.get("api_key"))
    ai_season_actions = ""
    ai_season_admin_editor = ""
    if selected_competition and selected_season and ai_configured and (
        not ai_season_summary or is_admin_user(ctx.current_user)
    ):
        ai_season_actions = f"""
        <form method="post" action="/competitions" class="m-0">
          <input type="hidden" name="action" value="generate_ai_season_summary">
          <input type="hidden" name="competition_name" value="{escape(selected_competition)}">
          <input type="hidden" name="season_name" value="{escape(selected_season)}">
          <input type="hidden" name="region_name" value="{escape(selected_region or '')}">
          <input type="hidden" name="series_slug" value="{escape(selected_series_slug or '')}">
          <button type="submit" class="btn btn-dark">{'重生成 AI 赛季总结' if ai_season_summary else '生成 AI 赛季总结'}</button>
        </form>
        """
    elif selected_competition and selected_season and not ai_configured and is_admin_user(ctx.current_user):
        ai_season_actions = '<a class="btn btn-outline-dark" href="/accounts">前往账号管理配置 AI 接口</a>'
    if selected_competition and selected_season and is_admin_user(ctx.current_user) and ai_season_summary:
        ai_season_admin_editor = f"""
        <div class="form-panel p-3 p-lg-4 mt-4">
          <h3 class="h5 mb-2">管理员编辑总结</h3>
          <p class="section-copy mb-3">可以直接修改当前赛季总结正文。保存后会立即覆盖展示内容。</p>
          <form method="post" action="/competitions">
            <input type="hidden" name="action" value="save_ai_season_summary">
            <input type="hidden" name="competition_name" value="{escape(selected_competition)}">
            <input type="hidden" name="season_name" value="{escape(selected_season)}">
            <input type="hidden" name="region_name" value="{escape(selected_region or '')}">
            <input type="hidden" name="series_slug" value="{escape(selected_series_slug or '')}">
            <div class="mb-3">
              <textarea class="form-control" name="summary_content" rows="14">{escape(ai_season_summary.get('content') or '')}</textarea>
            </div>
            <div class="d-flex flex-wrap gap-2">
              <button type="submit" class="btn btn-outline-dark">保存人工编辑</button>
            </div>
          </form>
        </div>
        """
    ai_season_summary_panel = ""
    if selected_season:
        ai_season_summary_panel = (
            f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
                <div>
                  <h2 class="section-title mb-2">AI 赛季总结</h2>
                  <p class="section-copy mb-0">基于当前赛事页下该赛季的已录入数据生成总结，可在补录后重新生成。</p>
                </div>
                <div class="d-flex flex-wrap gap-2">{ai_season_actions}</div>
              </div>
              <div class="small text-secondary mb-3">生成时间 {escape(ai_season_summary.get('generated_at') or '未生成')} · 模型 {escape(ai_season_summary.get('model') or ai_settings.get('model') or legacy.DEFAULT_AI_DAILY_BRIEF_MODEL)}</div>
              <div class="editorial-copy mb-0">{render_ai_daily_brief_html(ai_season_summary.get('content') or '')}</div>
              {ai_season_admin_editor}
            </section>
            """
            if ai_season_summary
            else f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3">
                <div>
                  <h2 class="section-title mb-2">AI 赛季总结</h2>
                  <p class="section-copy mb-0">{escape('当前赛季还没有生成 AI 总结，首次生成对所有访客开放。' if ai_configured else '当前还没有配置 AI 接口。配置后即可在这里生成赛季总结。')}</p>
                </div>
                <div class="d-flex flex-wrap gap-2">{ai_season_actions}</div>
              </div>
            </section>
            """
        )
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4"><div class="hero-layout"><div><div class="eyebrow mb-3">{escape(page_badge)}</div><h1 class="hero-title mb-3">{escape(hero_title)}</h1><p class="hero-copy mb-0">{escape(hero_intro)}</p>{region_switcher_html}{series_switcher_html}<div class="hero-switchers mt-3">{competition_switcher}</div>{season_switcher_html}<div class="hero-kpis"><div class="hero-pill"><span>参赛战队</span><strong>{len(team_rows)}</strong><small>{escape(selected_season or '当前赛季')} 真实参赛</small></div><div class="hero-pill"><span>参赛队员</span><strong>{player_count}</strong><small>{escape(selected_season or '当前赛季')} 已上场</small></div><div class="hero-pill"><span>赛季场次</span><strong>{len(match_rows)}</strong><small>{escape(scope_label)} 完整赛程</small></div></div></div><div class="hero-stage-card"><div class="official-mark">Event Sheet</div><div class="hero-stage-label">Season Overview</div><div class="hero-stage-title">{escape(scope_label)}</div><div class="hero-stage-note">{escape(hero_note)}</div><div class="hero-stage-grid"><div class="hero-stage-metric"><span>最近比赛日</span><strong>{escape(latest_played_on)}</strong><small>{escape(selected_season or (' / '.join(competition_meta['seasons'][:2]) if competition_meta and competition_meta['seasons'] else '赛季待录入'))}</small></div><div class="hero-stage-metric"><span>参赛战队</span><strong>{len(team_rows)}</strong><small>该赛季参赛战队</small></div><div class="hero-stage-metric"><span>参赛队员</span><strong>{player_count}</strong><small>该赛季实际出场</small></div><div class="hero-stage-metric"><span>赛季场次</span><strong>{len(match_rows)}</strong><small>该赛季完整赛程</small></div></div></div></div></section>
    {season_registration_panel}
    {ai_season_summary_panel}
    {leaderboard_sections}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h2 class="section-title mb-2">该赛季战队入口</h2><p class="section-copy mb-0">这里只保留当前赛季的战队名称入口，点进后继续看同一赛季口径下的战队详情。</p></div><div class="d-flex flex-wrap gap-2">{create_match_button}{edit_competition_button}{series_topic_button}{schedule_page_button}<a class="btn btn-outline-dark" href="{escape(build_scoped_path('/competitions', None, None, selected_region, selected_series_slug))}">返回地区赛事列表</a></div></div><div class="d-flex flex-wrap gap-2">{team_links_html or '<div class="alert alert-secondary mb-0 w-100">当前赛季还没有战队数据。</div>'}</div></section>
    <section class="panel shadow-sm p-3 p-lg-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h2 class="section-title mb-2">该赛季完整赛程</h2><p class="section-copy mb-0">按日历展示当前赛季的比赛日期；有比赛的日期会高亮显示，点击即可进入当天比赛结果页。</p></div></div>{season_schedule_calendar}</section>
    """
    return layout(scope_label, body, ctx, alert=alert)


def build_series_api_payload(
    ctx: RequestContext,
    series_slug: str,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if scope is None:
        scope, error_message = _build_series_scope(ctx, series_slug)
    else:
        error_message = ""
    if not scope:
        return {
            "error": error_message,
            "alert": form_value(ctx.query, "alert").strip(),
        }

    series_rows = scope["series_rows"]
    selected_season = scope["selected_season"]
    region_names = scope["region_names"]
    latest_played_on = scope["latest_played_on"]
    series_name = series_rows[0]["series_name"]
    return {
        "alert": form_value(ctx.query, "alert").strip(),
        "hero": {
            "title": series_name,
            "copy": "这里只保留赛季入口。先切换赛季，再进入对应地区赛事页查看该赛季的战队、赛程和比赛结果。",
            "selected_season": selected_season or "全部赛季",
            "latest_played_on": latest_played_on,
            "latest_copy": "当前赛季口径",
            "region_copy": f"覆盖地区：{'、'.join(region_names)}",
        },
        "filters": {
            "seasons": _serialize_series_season_links(
                series_slug,
                scope["season_names"],
                selected_season,
            ),
        },
        "metrics": [
            {
                "label": "覆盖地区",
                "value": str(len(series_rows)),
                "copy": "系列赛覆盖地区站点",
            },
            {
                "label": "当前赛季",
                "value": selected_season or "全部",
                "copy": "按赛季进入地区页",
            },
            {
                "label": "最近比赛日",
                "value": latest_played_on,
                "copy": "当前专题口径",
            },
        ],
        "management": {
            "can_manage_series": can_access_series_management(ctx.current_user),
            "manage_href": "/series-manage",
        },
        "cards": [
            _serialize_series_region_card(row, selected_season)
            for row in series_rows
        ],
        "legacy_href": _build_series_legacy_href(series_slug, selected_season),
        "back_href": build_scoped_path("/dashboard", None, None, DEFAULT_REGION_NAME, None),
    }


def get_series_legacy_page(ctx: RequestContext, series_slug: str) -> str:
    scope, error_message = _build_series_scope(ctx, series_slug)
    if not scope:
        return layout("未找到系列赛", f'<div class="alert alert-danger">{escape(error_message)}</div>', ctx)

    series_rows = scope["series_rows"]
    selected_season = scope["selected_season"]
    filtered_matches = scope["filtered_matches"]
    region_names = "、".join(scope["region_names"])
    latest_played_on = scope["latest_played_on"]
    season_switcher = build_series_season_switcher(series_slug, scope["season_names"], selected_season)
    season_switcher_html = f'<div class="hero-switchers mt-4">{season_switcher}</div>' if season_switcher else ""
    region_cards = []
    for row in series_rows:
        competition_path = build_scoped_path("/competitions", row["competition_name"], selected_season if selected_season in row["seasons"] else None, row["region_name"], row["series_slug"])
        region_cards.append(f"""<div class="col-12 col-lg-6"><a class="team-link-card shadow-sm p-4 h-100" href="{escape(competition_path)}"><div class="d-flex justify-content-between align-items-start gap-3"><div><div class="card-kicker mb-2">{escape(row['region_name'])} · Regional Event</div><h2 class="h4 mb-2">{escape(row['competition_name'])}</h2><div class="small-muted mb-2">赛季 {escape('、'.join(row['seasons'])) if row['seasons'] else '待录入'}</div><div class="small-muted">最近比赛日 {escape(row['latest_played_on'] or '待更新')}</div></div><span class="chip">进入地区赛事页</span></div><div class="row g-3 mt-2"><div class="col-4"><div class="small text-secondary">战队</div><div class="fw-semibold">{row['team_count']} 支</div></div><div class="col-4"><div class="small text-secondary">队员</div><div class="fw-semibold">{row['player_count']} 名</div></div><div class="col-4"><div class="small text-secondary">对局</div><div class="fw-semibold">{row['match_count']} 场</div></div></div></a></div>""")
    manage_button = '<a class="btn btn-outline-dark" href="/series-manage">维护系列赛目录</a>' if can_access_series_management(ctx.current_user) else ""
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4"><div class="hero-layout"><div><div class="eyebrow mb-3">系列赛专题页</div><h1 class="hero-title mb-3">{escape(series_rows[0]['series_name'])}</h1><p class="hero-copy mb-0">这里只保留赛季入口。先切换赛季，再进入对应地区赛事页查看该赛季的战队、赛程和比赛结果。</p>{season_switcher_html}<div class="hero-kpis"><div class="hero-pill"><span>覆盖地区</span><strong>{len(series_rows)}</strong><small>{escape(region_names)}</small></div><div class="hero-pill"><span>当前赛季</span><strong>{escape(selected_season or '全部赛季')}</strong><small>按赛季进入地区页</small></div><div class="hero-pill"><span>最近比赛日</span><strong>{escape(latest_played_on)}</strong><small>当前赛季口径</small></div></div></div><div class="hero-stage-card"><div class="official-mark">Series Entry</div><div class="hero-stage-label">Season Entry</div><div class="hero-stage-title">{escape(selected_season or '全部赛季')}</div><div class="hero-stage-note">点击下方任一地区赛事页入口，即可进入该地区当前赛季页面。</div><div class="hero-stage-grid"><div class="hero-stage-metric"><span>地区站点</span><strong>{len(series_rows)}</strong><small>系列赛覆盖地区</small></div><div class="hero-stage-metric"><span>赛季</span><strong>{escape(selected_season or '全部')}</strong><small>当前专题筛选</small></div></div></div></div></section>
    <section class="panel shadow-sm p-3 p-lg-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h2 class="section-title mb-2">赛季入口</h2><p class="section-copy mb-0">选择一个地区赛事页进入该赛季详情。</p></div><div class="d-flex flex-wrap gap-2">{manage_button}<a class="btn btn-outline-dark" href="{escape(build_scoped_path('/dashboard', None, None, DEFAULT_REGION_NAME, None))}">返回首页</a></div></div><div class="row g-3 g-lg-4">{''.join(region_cards)}</div></section>
    """
    return layout(f"{series_rows[0]['series_name']} 专题页", body, ctx)


def get_series_page(ctx: RequestContext, series_slug: str) -> str:
    return build_series_frontend_page(ctx, series_slug)


def handle_series_api(ctx: RequestContext, start_response, series_slug: str):
    scope, error_message = _build_series_scope(ctx, series_slug)
    if not scope:
        return start_response_json(
            start_response,
            "404 Not Found",
            {
                "error": error_message,
                "alert": form_value(ctx.query, "alert").strip(),
            },
        )
    return start_response_json(
        start_response,
        "200 OK",
        build_series_api_payload(ctx, series_slug, scope),
    )


def _build_match_day_scope(ctx: RequestContext, played_on: str) -> tuple[dict[str, Any] | None, str]:
    if not is_valid_match_day(played_on):
        return None, "比赛日期格式不正确。"

    data = load_validated_data()
    catalog = load_series_catalog(data)
    player_lookup = {player["player_id"]: player for player in data["players"]}
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    completed_day_matches, day_player_rows, day_team_rows = build_match_day_leaderboards(data, played_on)
    day_matches = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (
                get_match_competition_name(item),
                (item.get("season") or "").strip(),
                item["round"],
                item["game_no"],
                item["match_id"],
            ),
        )
        if str(match.get("played_on") or "").strip() == played_on
    ]
    if not day_matches:
        return None, "这一天还没有比赛记录。"

    grouped_matches: dict[str, list[dict[str, Any]]] = {}
    for match in day_matches:
        grouped_matches.setdefault(get_match_competition_name(match), []).append(match)

    next_path = legacy.form_value(ctx.query, "next").strip() or "/dashboard"
    ai_settings = load_ai_daily_brief_settings()
    ai_report = load_ai_match_day_report(played_on)
    return (
        {
            "data": data,
            "catalog": catalog,
            "player_lookup": player_lookup,
            "team_lookup": team_lookup,
            "completed_day_matches": completed_day_matches,
            "day_player_rows": day_player_rows,
            "day_team_rows": day_team_rows,
            "day_matches": day_matches,
            "grouped_matches": grouped_matches,
            "next_path": next_path,
            "ai_settings": ai_settings,
            "ai_report": ai_report,
        },
        "",
    )


def _build_match_day_legacy_href(played_on: str, next_path: str | None) -> str:
    base_path = f"/days/{played_on}/legacy"
    if not next_path:
        return base_path
    return f"{base_path}?{legacy.urlencode({'next': next_path})}"


def _serialize_day_team_row(
    row: dict[str, Any],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    competition_name = str(row.get("competition_name") or "").strip()
    season_name = str(row.get("season_name") or "").strip()
    series_entry = get_series_entry_by_competition(catalog, competition_name)
    region_name = series_entry["region_name"] if series_entry else DEFAULT_REGION_NAME
    series_slug = series_entry["series_slug"] if series_entry else None
    return {
        "rank": row.get("points_rank", "-"),
        "name": row["name"],
        "matches_represented": int(row["matches_represented"]),
        "win_rate": format_pct(row["win_rate"]),
        "points_total": f'{row["points_earned_total"]:.2f}',
        "href": build_scoped_path(
            "/teams/" + row["team_id"],
            competition_name,
            season_name,
            region_name,
            series_slug,
        ),
    }


def _serialize_day_match_competition_section(
    played_on: str,
    competition_name: str,
    matches: list[dict[str, Any]],
    catalog: dict[str, Any],
    player_lookup: dict[str, dict[str, Any]],
    team_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    series_entry = get_series_entry_by_competition(catalog, competition_name)
    region_name = series_entry["region_name"] if series_entry else DEFAULT_REGION_NAME
    series_name = series_entry["series_name"] if series_entry else competition_name
    series_slug = series_entry["series_slug"] if series_entry else None
    player_count = len({entry["player_id"] for match in matches for entry in match["players"]})
    team_count = len({entry["team_id"] for match in matches for entry in match["players"]})
    completed_count = sum(1 for match in matches if is_match_counted_as_played(match))

    serialized_matches: list[dict[str, Any]] = []
    for match in sorted(
        matches,
        key=lambda item: (
            (item.get("season") or "").strip(),
            item["round"],
            item["game_no"],
            item["match_id"],
        ),
    ):
        season_name = (match.get("season") or "").strip()
        detail_path = build_match_day_path(played_on)
        participants = []
        for participant in sorted(
            match["players"],
            key=lambda item: (
                -float(item["points_earned"]),
                item["seat"],
                player_lookup.get(item["player_id"], {}).get("display_name", item["player_id"]),
            ),
        ):
            player_name = player_lookup.get(participant["player_id"], {}).get("display_name", participant["player_id"])
            team_name = team_lookup.get(participant["team_id"], {}).get("name", participant["team_id"])
            participants.append(
                {
                    "seat": participant["seat"],
                    "player_name": player_name,
                    "player_href": build_scoped_path(
                        "/players/" + participant["player_id"],
                        competition_name,
                        season_name,
                        region_name,
                        series_slug,
                    ),
                    "team_name": team_name,
                    "team_href": build_scoped_path(
                        "/teams/" + participant["team_id"],
                        competition_name,
                        season_name,
                        region_name,
                        series_slug,
                    ),
                    "role": participant["role"],
                    "result": RESULT_OPTIONS.get(participant["result"], participant["result"]),
                    "points": f'{float(participant["points_earned"]):.2f}',
                }
            )
        represented_teams = sorted(
            {
                item["team_id"]: item
                for item in match["players"]
                if item["team_id"] in team_lookup
            }.values(),
            key=lambda item: team_lookup[item["team_id"]]["name"],
        )
        meta_parts = [
            "参赛战队 "
            + "、".join(team_lookup[item["team_id"]]["name"] for item in represented_teams)
            if represented_teams
            else "参赛战队待补全"
        ]
        table_label = str(match.get("table_label") or "").strip()
        if table_label:
            meta_parts.append(table_label)
        duration_minutes = int(match.get("duration_minutes") or 0)
        if duration_minutes:
            meta_parts.append(f"{duration_minutes} 分钟")
        if not is_match_counted_as_played(match):
            meta_parts.append("待补录")
        serialized_matches.append(
            {
                "match_id": match["match_id"],
                "season_name": season_name,
                "stage_label": STAGE_OPTIONS.get(match["stage"], match["stage"]),
                "round": int(match["round"]),
                "game_no": int(match["game_no"]),
                "meta_text": " · ".join(meta_parts),
                "detail_href": f"/matches/{match['match_id']}?next={quote(detail_path)}",
                "participants": participants,
            }
        )

    return {
        "series_name": series_name,
        "region_name": region_name,
        "competition_name": competition_name,
        "copy": f"当天该系列赛共有 {len(matches)} 场比赛，其中 {completed_count} 场已完成补录，涉及 {team_count} 支战队、{player_count} 名队员。",
        "competition_href": build_scoped_path(
            "/competitions",
            competition_name,
            (matches[0].get("season") or "").strip() or None,
            region_name,
            series_slug,
        ),
        "matches": serialized_matches,
    }


def build_match_day_frontend_page(ctx: RequestContext, played_on: str) -> str:
    if ctx.current_user:
        display_name = ctx.current_user.get("display_name") or ctx.current_user["username"]
        role_label = account_role_label(ctx.current_user)
        account_html = f"""
        <div class="shell-account">
          <span class="shell-account-label">{escape(display_name)} · {escape(role_label)}</span>
          <a class="shell-button shell-button-secondary" href="/profile">控制台</a>
          <form method="post" action="/logout" class="shell-inline-form">
            <button type="submit" class="shell-button shell-button-secondary">退出</button>
          </form>
        </div>
        """
    else:
        account_html = """
        <div class="shell-account">
          <a class="shell-button shell-button-secondary" href="/login">登录</a>
          <a class="shell-button shell-button-primary" href="/register">注册</a>
        </div>
        """

    bootstrap = json.dumps(
        {
            "apiEndpoint": f"/api/days/{played_on}",
            "alert": form_value(ctx.query, "alert").strip(),
        },
        ensure_ascii=False,
    )
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#dceef7">
    <title>{escape(played_on)} 比赛日</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/competitions-app.css">
  </head>
  <body class="competitions-app-shell">
    <div class="shell-backdrop"></div>
    <header class="shell-header">
      <div class="shell-brand">
        <a class="shell-brand-link" href="{escape(build_match_day_path(played_on))}">{escape(played_on)} 比赛日</a>
        <span class="shell-brand-copy">Match Day Frontend · API Driven</span>
      </div>
      <nav class="shell-nav" aria-label="主导航">
        <a class="shell-nav-link" href="/dashboard">首页</a>
        <a class="shell-nav-link" href="/competitions">比赛页面</a>
        <a class="shell-nav-link is-active" href="{escape(build_match_day_path(played_on))}">比赛日</a>
      </nav>
      {account_html}
    </header>
    <main id="match-day-app" class="competitions-app-root" aria-live="polite">
      <section class="competitions-loading-shell">
        <div class="competitions-loading-kicker">Loading Match Day</div>
        <h1>正在加载比赛日页面</h1>
        <p>新前端会通过独立 API 拉取当天战队日榜、AI 日报和比赛结果明细。</p>
      </section>
    </main>
    <script>window.__WEREWOLF_MATCH_DAY_BOOTSTRAP__ = {bootstrap};</script>
    <script src="/assets/day-app.js" defer></script>
  </body>
</html>
"""


def build_match_day_api_payload(
    ctx: RequestContext,
    played_on: str,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if scope is None:
        scope, error_message = _build_match_day_scope(ctx, played_on)
    else:
        error_message = ""
    if not scope:
        return {
            "error": error_message,
            "alert": form_value(ctx.query, "alert").strip(),
        }

    grouped_matches = scope["grouped_matches"]
    completed_day_matches = scope["completed_day_matches"]
    total_team_count = len({entry["team_id"] for match in completed_day_matches for entry in match["players"]})
    total_player_count = len({entry["player_id"] for match in completed_day_matches for entry in match["players"]})
    ai_settings = scope["ai_settings"]
    ai_report = scope["ai_report"]
    ai_configured = bool(ai_settings.get("base_url") and ai_settings.get("api_key"))
    next_path = scope["next_path"]
    action_path = build_match_day_path(played_on, next_path)
    return {
        "alert": form_value(ctx.query, "alert").strip(),
        "hero": {
            "title": f"{played_on} 比赛日",
            "copy": "这里按系列赛拆分展示这一天的全部比赛结果，只保留当天各局比赛明细。",
        },
        "metrics": [
            {
                "label": "系列赛数量",
                "value": str(len(grouped_matches)),
                "copy": "当天涉及系列赛",
            },
            {
                "label": "比赛场次",
                "value": str(len(scope["day_matches"])),
                "copy": "当天全部比赛",
            },
            {
                "label": "已补录场次",
                "value": str(len(completed_day_matches)),
                "copy": "已完成成绩录入",
            },
            {
                "label": "上场队员",
                "value": str(total_player_count),
                "copy": "已补录比赛口径",
            },
        ],
        "hero_side": {
            "played_on": played_on,
            "series_count": str(len(grouped_matches)),
            "match_count": str(len(scope["day_matches"])),
            "team_count": str(total_team_count),
            "player_count": str(total_player_count),
        },
        "ai_report": {
            "exists": bool(ai_report),
            "configured": ai_configured,
            "can_generate": ai_configured and (not ai_report or is_admin_user(ctx.current_user)),
            "can_edit": bool(is_admin_user(ctx.current_user) and ai_report),
            "action_path": action_path,
            "configure_href": "/accounts" if is_admin_user(ctx.current_user) and not ai_configured else "",
            "generate_label": "重生成 AI 日报" if ai_report else "生成 AI 日报",
            "generated_at": (ai_report or {}).get("generated_at") or "未生成",
            "model": (ai_report or {}).get("model") or ai_settings.get("model") or legacy.DEFAULT_AI_DAILY_BRIEF_MODEL,
            "html": render_ai_daily_brief_html((ai_report or {}).get("content") or "") if ai_report else "",
            "content": (ai_report or {}).get("content") or "",
            "empty_copy": (
                "当前还没有生成日报，首次生成对所有访客开放。"
                if ai_configured
                else f'当前还没有配置 AI 接口。{("已保存 Key " + mask_api_key(ai_settings.get("api_key") or "")) if ai_settings.get("api_key") else ""}'
            ),
        },
        "team_leaderboard": [
            _serialize_day_team_row(row, scope["catalog"])
            for row in scope["day_team_rows"]
        ],
        "competitions": [
            _serialize_day_match_competition_section(
                played_on,
                competition_name,
                matches,
                scope["catalog"],
                scope["player_lookup"],
                scope["team_lookup"],
            )
            for competition_name, matches in grouped_matches.items()
        ],
        "back_href": next_path,
        "legacy_href": _build_match_day_legacy_href(played_on, next_path),
    }


def get_match_day_page(ctx: RequestContext, played_on: str) -> str:
    return build_match_day_frontend_page(ctx, played_on)


def render_ai_daily_brief_html(content: str) -> str:
    return legacy.render_ai_daily_brief_html(content)


def build_ai_match_day_prompt(
    played_on: str,
    day_matches: list[dict[str, Any]],
    day_team_rows: list[dict[str, Any]],
    day_player_rows: list[dict[str, Any]],
    player_lookup: dict[str, dict[str, Any]],
    team_lookup: dict[str, dict[str, Any]],
) -> str:
    prompt_templates = load_ai_prompt_templates()
    grouped_matches: dict[str, list[dict[str, Any]]] = {}
    for match in day_matches:
        grouped_matches.setdefault(get_match_competition_name(match), []).append(match)

    match_lines: list[str] = []
    for competition_name, matches in grouped_matches.items():
        match_lines.append(f"[赛事] {competition_name}")
        for match in sorted(
            matches,
            key=lambda item: (
                (item.get("season") or "").strip(),
                item["round"],
                item["game_no"],
                item["match_id"],
            ),
        ):
            participant_lines = []
            team_points: dict[str, float] = {}
            for participant in match["players"]:
                team_id = str(participant.get("team_id") or "").strip()
                player_id = str(participant.get("player_id") or "").strip()
                team_name = team_lookup.get(team_id, {}).get("name", team_id or "未知战队")
                player_name = player_lookup.get(player_id, {}).get("display_name", player_id or "未知队员")
                team_points[team_name] = team_points.get(team_name, 0.0) + float(participant.get("points_earned") or 0.0)
                participant_lines.append(
                    f"- {participant.get('seat', '-')}号 {player_name} / {team_name} / 角色 {participant.get('role', '-')}"
                    f" / 结果 {RESULT_OPTIONS.get(participant.get('result'), participant.get('result', '-'))} / 积分 {float(participant.get('points_earned') or 0.0):.2f}"
                )
            team_score_summary = "；".join(
                f"{team_name} {points:.2f}"
                for team_name, points in sorted(team_points.items(), key=lambda item: (-item[1], item[0]))
            )
            match_lines.append(
                f"比赛 {match['match_id']} | 赛季 {(match.get('season') or '').strip()} | "
                f"{STAGE_OPTIONS.get(match.get('stage'), match.get('stage'))} | 第 {match['round']} 轮 / 第 {match['game_no']} 局 | "
                f"台次 {(match.get('table_label') or '').strip() or '未标注'} | 战队总分 {team_score_summary or '待补录'}"
            )
            match_lines.extend(participant_lines)

    team_board_lines = [
        f"- 第{row.get('points_rank', '-')}名 {row.get('name', row.get('team_id', '未知战队'))} | "
        f"{row.get('competition_name', '')} / {row.get('season_name', '')} | "
        f"场次 {row.get('matches_represented', 0)} | 胜率 {format_pct(row.get('win_rate', 0.0))} | 总积分 {float(row.get('points_earned_total', 0.0)):.2f}"
        for row in day_team_rows[:8]
    ]
    player_board_lines = [
        f"- 第{row.get('rank', '-')}名 {row.get('display_name', row.get('player_id', '未知队员'))} | "
        f"{row.get('team_name', row.get('team_id', '未知战队'))} | "
        f"{row.get('competition_name', '')} / {row.get('season_name', '')} | "
        f"场次 {row.get('games_played', 0)} | 总积分 {float(row.get('points_earned_total', 0.0)):.2f} | 胜率 {format_pct(row.get('win_rate', 0.0))}"
        for row in day_player_rows[:10]
    ]
    return render_ai_prompt_template(
        prompt_templates["match_day_user_prompt"],
        {
            "played_on": played_on,
            "series_count": len(grouped_matches),
            "match_count": len(day_matches),
            "team_board": "\n".join(team_board_lines) if team_board_lines else "- 暂无战队榜数据",
            "player_board": "\n".join(player_board_lines) if player_board_lines else "- 暂无队员榜数据",
            "match_details": "\n".join(match_lines) if match_lines else "- 暂无比赛明细",
        },
        "比赛日报用户提示词模板",
    )


def generate_ai_match_day_report(
    played_on: str,
    day_matches: list[dict[str, Any]],
    day_team_rows: list[dict[str, Any]],
    day_player_rows: list[dict[str, Any]],
    player_lookup: dict[str, dict[str, Any]],
    team_lookup: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    settings = load_ai_daily_brief_settings()
    prompt_templates = load_ai_prompt_templates()
    base_url = str(settings.get("base_url") or "").strip()
    api_key = str(settings.get("api_key") or "").strip()
    model = str(settings.get("model") or legacy.DEFAULT_AI_DAILY_BRIEF_MODEL).strip() or legacy.DEFAULT_AI_DAILY_BRIEF_MODEL
    if not base_url or not api_key:
        raise ValueError("AI 比赛日报尚未配置 Base URL 或 API Key。")
    user_prompt = build_ai_match_day_prompt(
        played_on,
        day_matches,
        day_team_rows,
        day_player_rows,
        player_lookup,
        team_lookup,
    )
    report_text = request_openai_compatible_completion(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=prompt_templates["match_day_system_prompt"],
        user_prompt=user_prompt,
    )
    return report_text, model


def build_ai_season_summary_prompt(
    competition_name: str,
    season_name: str,
    match_rows: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
    player_rows: list[dict[str, Any]],
    stage_team_rows: dict[str, list[dict[str, Any]]],
    mvp_rows: list[dict[str, Any]],
) -> str:
    prompt_templates = load_ai_prompt_templates()
    stage_lines = []
    for stage_key, rows in stage_team_rows.items():
        top_rows = rows[:4]
        if not top_rows:
            continue
        summary = "；".join(
            f"{row['name']} 总积分 {float(row['points_earned_total']):.2f} / 胜率 {format_pct(row['win_rate'])}"
            for row in top_rows
        )
        stage_lines.append(f"- {STAGE_OPTIONS.get(stage_key, stage_key)}：{summary}")
    top_team_lines = [
        f"- 第{row.get('points_rank', '-')}名 {row['name']} | 场次 {row['matches_represented']} | 上场队员 {row['player_count']} | 总积分 {float(row['points_earned_total']):.2f} | 胜率 {format_pct(row['win_rate'])}"
        for row in team_rows[:8]
    ]
    top_player_lines = [
        f"- 第{row['rank']}名 {row['display_name']} | {row['team_name']} | 出场 {row['games_played']} | 战绩 {row['record']} | 总积分 {float(row['points_earned_total']):.2f} | 场均 {float(row['average_points']):.2f}"
        for row in player_rows[:10]
    ]
    mvp_lines = [
        f"- 第{row['rank']}名 {row['display_name']} | {row['team_name']} | MVP {row['mvp_count']} 次 | 最近获奖 {row.get('latest_awarded_on') or '待更新'}"
        for row in mvp_rows[:8]
    ]
    match_day_lines = []
    seen_days: list[str] = []
    for match in sorted(
        match_rows,
        key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
    ):
        played_on = str(match.get("played_on") or "").strip()
        if played_on and played_on not in seen_days:
            seen_days.append(played_on)
    for played_on in seen_days[:12]:
        day_count = sum(1 for match in match_rows if str(match.get("played_on") or "").strip() == played_on)
        match_day_lines.append(f"- {played_on}：{day_count} 场")
    return render_ai_prompt_template(
        prompt_templates["season_summary_user_prompt"],
        {
            "competition_name": competition_name,
            "season_name": season_name,
            "match_count": len(match_rows),
            "team_count": len(team_rows),
            "player_count": len({row["player_id"] for row in player_rows}) if player_rows else 0,
            "team_board": "\n".join(top_team_lines) if top_team_lines else "- 暂无战队积分数据",
            "player_board": "\n".join(top_player_lines) if top_player_lines else "- 暂无个人积分数据",
            "mvp_board": "\n".join(mvp_lines) if mvp_lines else "- 暂无 MVP 数据",
            "stage_summary": "\n".join(stage_lines) if stage_lines else "- 暂无赛段积分数据",
            "match_day_distribution": "\n".join(match_day_lines) if match_day_lines else "- 暂无比赛日数据",
        },
        "赛季总结用户提示词模板",
    )


def generate_ai_season_summary(
    competition_name: str,
    season_name: str,
    match_rows: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
    player_rows: list[dict[str, Any]],
    stage_team_rows: dict[str, list[dict[str, Any]]],
    mvp_rows: list[dict[str, Any]],
) -> tuple[str, str]:
    settings = load_ai_daily_brief_settings()
    prompt_templates = load_ai_prompt_templates()
    base_url = str(settings.get("base_url") or "").strip()
    api_key = str(settings.get("api_key") or "").strip()
    model = str(settings.get("model") or legacy.DEFAULT_AI_DAILY_BRIEF_MODEL).strip() or legacy.DEFAULT_AI_DAILY_BRIEF_MODEL
    if not base_url or not api_key:
        raise ValueError("AI 赛季总结尚未配置 Base URL 或 API Key。")
    report_text = request_openai_compatible_completion(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=prompt_templates["season_summary_system_prompt"],
        user_prompt=build_ai_season_summary_prompt(
            competition_name,
            season_name,
            match_rows,
            team_rows,
            player_rows,
            stage_team_rows,
            mvp_rows,
        ),
    )
    return report_text, model


def get_match_day_page_with_alert(ctx: RequestContext, played_on: str, alert: str = "") -> str:
    if not is_valid_match_day(played_on):
        return layout("未找到比赛日", '<div class="alert alert-danger">比赛日期格式不正确。</div>', ctx, alert=alert)

    data = load_validated_data()
    catalog = load_series_catalog(data)
    player_lookup = {player["player_id"]: player for player in data["players"]}
    completed_day_matches, day_player_rows, day_team_rows = build_match_day_leaderboards(data, played_on)
    day_matches = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (
                get_match_competition_name(item),
                (item.get("season") or "").strip(),
                item["round"],
                item["game_no"],
                item["match_id"],
            ),
        )
        if str(match.get("played_on") or "").strip() == played_on
    ]
    if not day_matches:
        return layout("未找到比赛日", '<div class="alert alert-danger">这一天还没有比赛记录。</div>', ctx, alert=alert)

    team_lookup = {team["team_id"]: team for team in data["teams"]}
    next_path = legacy.form_value(ctx.query, "next").strip() or "/dashboard"
    grouped_matches: dict[str, list[dict[str, Any]]] = {}
    for match in day_matches:
        grouped_matches.setdefault(get_match_competition_name(match), []).append(match)

    competition_sections = []
    for competition_name, matches in grouped_matches.items():
        series_entry = get_series_entry_by_competition(catalog, competition_name)
        region_name = series_entry["region_name"] if series_entry else DEFAULT_REGION_NAME
        series_name = series_entry["series_name"] if series_entry else competition_name
        series_slug = series_entry["series_slug"] if series_entry else None
        player_count = len({entry["player_id"] for match in matches for entry in match["players"]})
        team_count = len({entry["team_id"] for match in matches for entry in match["players"]})
        completed_count = sum(1 for match in matches if is_match_counted_as_played(match))
        match_cards = []
        for match in sorted(
            matches,
            key=lambda item: ((item.get("season") or "").strip(), item["round"], item["game_no"], item["match_id"]),
        ):
            season_name = (match.get("season") or "").strip()
            detail_path = build_match_day_path(played_on)
            match_detail_path = f"/matches/{match['match_id']}?next={quote(detail_path)}"
            completed = is_match_counted_as_played(match)
            team_links = "、".join(
                f'<a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{legacy.escape(build_scoped_path("/teams/" + entry["team_id"], competition_name, season_name, region_name, series_slug))}">{legacy.escape(team_lookup[entry["team_id"]]["name"])}</a>'
                for entry in sorted(
                    {
                        item["team_id"]: item
                        for item in match["players"]
                        if item["team_id"] in team_lookup
                    }.values(),
                    key=lambda item: team_lookup[item["team_id"]]["name"],
                )
            )
            player_rows = []
            for participant in sorted(
                match["players"],
                key=lambda item: (
                    -float(item["points_earned"]),
                    item["seat"],
                    player_lookup.get(item["player_id"], {}).get("display_name", item["player_id"]),
                ),
            ):
                player_name = player_lookup.get(participant["player_id"], {}).get("display_name", participant["player_id"])
                team_name = team_lookup.get(participant["team_id"], {}).get("name", participant["team_id"])
                player_rows.append(
                    f"""
                    <tr>
                      <td>{participant['seat']}</td>
                      <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{legacy.escape(build_scoped_path('/players/' + participant['player_id'], competition_name, season_name, region_name, series_slug))}">{legacy.escape(player_name)}</a></td>
                      <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{legacy.escape(build_scoped_path('/teams/' + participant['team_id'], competition_name, season_name, region_name, series_slug))}">{legacy.escape(team_name)}</a></td>
                      <td>{legacy.escape(participant['role'])}</td>
                      <td>{legacy.escape(RESULT_OPTIONS.get(participant['result'], participant['result']))}</td>
                      <td>{float(participant['points_earned']):.2f}</td>
                    </tr>
                    """
                )
            meta_parts = [f"参赛战队 {team_links}" if team_links else "参赛战队待补全"]
            table_label = str(match.get("table_label") or "").strip()
            if table_label:
                meta_parts.append(legacy.escape(table_label))
            duration_minutes = int(match.get("duration_minutes") or 0)
            if duration_minutes:
                meta_parts.append(f"{duration_minutes} 分钟")
            if not completed:
                meta_parts.append("待补录")
            match_cards.append(
                f"""
                <div class="col-12">
                  <div class="team-link-card shadow-sm p-4 h-100">
                    <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-start gap-3 mb-3">
                      <div>
                        <div class="card-kicker mb-2">比赛结果</div>
                        <h3 class="h5 mb-2">{legacy.escape(match['match_id'])}</h3>
                        <div class="small-muted">赛季 {legacy.escape(season_name)} · {legacy.escape(STAGE_OPTIONS.get(match['stage'], match['stage']))} · 第 {match['round']} 轮 / 第 {match['game_no']} 局</div>
                        <div class="small-muted mt-1">{' · '.join(meta_parts)}</div>
                      </div>
                      <div class="d-flex flex-wrap gap-2">
                        <a class="btn btn-sm btn-outline-dark" href="{legacy.escape(match_detail_path)}">查看详情</a>
                      </div>
                    </div>
                    <div class="table-responsive">
                      <table class="table align-middle mb-0">
                        <thead>
                          <tr>
                            <th>座位</th>
                            <th>队员</th>
                            <th>战队</th>
                            <th>角色</th>
                            <th>结果</th>
                            <th>个人积分</th>
                          </tr>
                        </thead>
                        <tbody>
                          {''.join(player_rows) or '<tr><td colspan="6" class="text-secondary">当前比赛还没有完成补录。</td></tr>'}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
                """
            )

        competition_sections.append(
            f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
                <div>
                  <h2 class="section-title mb-2">{legacy.escape(series_name)} · {legacy.escape(region_name)}</h2>
                  <div class="small-muted mb-2">{legacy.escape(competition_name)}</div>
                  <p class="section-copy mb-0">当天该系列赛共有 {len(matches)} 场比赛，其中 {completed_count} 场已完成补录，涉及 {team_count} 支战队、{player_count} 名队员。下方只展示当天每场比赛的结果明细。</p>
                </div>
                <a class="btn btn-outline-dark" href="{legacy.escape(build_scoped_path('/competitions', competition_name, (matches[0].get('season') or '').strip() or None, region_name, series_slug))}">进入该赛事页</a>
              </div>
              <div class="row g-3">{''.join(match_cards)}</div>
            </section>
            """
        )

    total_team_count = len({entry["team_id"] for match in completed_day_matches for entry in match["players"]})
    total_player_count = len({entry["player_id"] for match in completed_day_matches for entry in match["players"]})
    team_day_rows = []
    for row in day_team_rows:
        competition_name = str(row.get("competition_name") or "").strip()
        season_name = str(row.get("season_name") or "").strip()
        series_entry = get_series_entry_by_competition(catalog, competition_name)
        region_name = series_entry["region_name"] if series_entry else DEFAULT_REGION_NAME
        series_slug = series_entry["series_slug"] if series_entry else None
        team_day_rows.append(
            f"""
            <tr>
              <td>{row.get('points_rank', '-')}</td>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{legacy.escape(build_scoped_path('/teams/' + row['team_id'], competition_name, season_name, region_name, series_slug))}">{legacy.escape(row['name'])}</a></td>
              <td>{row['matches_represented']}</td>
              <td>{format_pct(row['win_rate'])}</td>
              <td>{row['points_earned_total']:.2f}</td>
            </tr>
            """
        )
    team_day_panel = (
        f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">战队积分日榜</h2>
              <p class="section-copy mb-0">只统计当天已完成补录的比赛，默认按总积分从高到低排序。</p>
            </div>
          </div>
          <div class="table-responsive">
            <table class="table align-middle is-mobile-stack">
              <thead>
                <tr>
                  <th>排名</th>
                  <th>战队</th>
                  <th>场次</th>
                  <th>胜率</th>
                  <th>总积分</th>
                </tr>
              </thead>
              <tbody>{''.join(team_day_rows)}</tbody>
            </table>
          </div>
        </section>
        """
        if team_day_rows
        else ""
    )
    ai_settings = load_ai_daily_brief_settings()
    ai_report = load_ai_match_day_report(played_on)
    ai_configured = bool(ai_settings.get("base_url") and ai_settings.get("api_key"))
    ai_actions = ""
    ai_report_admin_editor = ""
    if ai_configured and (not ai_report or is_admin_user(ctx.current_user)):
        ai_actions = f"""
        <form method="post" action="{escape(build_match_day_path(played_on, next_path))}" class="m-0">
          <input type="hidden" name="action" value="generate_ai_daily_brief">
          <button type="submit" class="btn btn-dark">{'重生成 AI 日报' if ai_report else '生成 AI 日报'}</button>
        </form>
        """
    elif not ai_configured and is_admin_user(ctx.current_user):
        ai_actions = '<a class="btn btn-outline-dark" href="/accounts">前往账号管理配置 AI 接口</a>'
    if is_admin_user(ctx.current_user) and ai_report:
        ai_report_admin_editor = f"""
        <div class="form-panel p-3 p-lg-4 mt-4">
          <h3 class="h5 mb-2">管理员编辑日报</h3>
          <p class="section-copy mb-3">可以直接修改当前日报正文。保存后会立即覆盖展示内容。</p>
          <form method="post" action="{escape(build_match_day_path(played_on, next_path))}">
            <input type="hidden" name="action" value="save_ai_daily_brief">
            <div class="mb-3">
              <textarea class="form-control" name="report_content" rows="12">{escape(ai_report.get('content') or '')}</textarea>
            </div>
            <div class="d-flex flex-wrap gap-2">
              <button type="submit" class="btn btn-outline-dark">保存人工编辑</button>
            </div>
          </form>
        </div>
        """
    ai_report_panel = (
        f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">AI 比赛日报</h2>
              <p class="section-copy mb-0">基于当天已录入比赛数据生成的简版赛事日报，可随比赛补录进度反复重生成。</p>
            </div>
            <div class="d-flex flex-wrap gap-2">{ai_actions}</div>
          </div>
          <div class="small text-secondary mb-3">生成时间 {escape(ai_report.get('generated_at') or '未生成')} · 模型 {escape(ai_report.get('model') or ai_settings.get('model') or legacy.DEFAULT_AI_DAILY_BRIEF_MODEL)}</div>
          <div class="editorial-copy mb-0">{render_ai_daily_brief_html(ai_report.get('content') or '')}</div>
          {ai_report_admin_editor}
        </section>
        """
        if ai_report
        else f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3">
                <div>
                  <h2 class="section-title mb-2">AI 比赛日报</h2>
                  <p class="section-copy mb-0">{escape('当前还没有生成日报，首次生成对所有访客开放。' if ai_configured else f'当前还没有配置 AI 接口。{("已保存 Key " + mask_api_key(ai_settings.get("api_key") or "")) if ai_settings.get("api_key") else ""}')}</p>
                </div>
                <div class="d-flex flex-wrap gap-2">{ai_actions}</div>
              </div>
            </section>
        """
    )
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">比赛日总览</div>
          <h1 class="hero-title mb-3">{legacy.escape(played_on)} 比赛日</h1>
          <p class="hero-copy mb-0">这里按系列赛拆分展示这一天的全部比赛结果，只保留当天各局比赛明细。</p>
          <div class="d-flex flex-wrap gap-2 mt-4">
            <a class="btn btn-outline-dark" href="{legacy.escape(next_path)}">返回上一页</a>
          </div>
          <div class="hero-kpis">
            <div class="hero-pill"><span>系列赛数量</span><strong>{len(grouped_matches)}</strong><small>当天涉及系列赛</small></div>
            <div class="hero-pill"><span>比赛场次</span><strong>{len(day_matches)}</strong><small>当天全部比赛</small></div>
            <div class="hero-pill"><span>已补录场次</span><strong>{len(completed_day_matches)}</strong><small>已完成成绩录入</small></div>
            <div class="hero-pill"><span>上场队员</span><strong>{total_player_count}</strong><small>已补录比赛口径</small></div>
          </div>
        </div>
        <div class="hero-stage-card">
          <div class="official-mark">Match Day</div>
          <div class="hero-stage-label">Daily Overview</div>
          <div class="hero-stage-title">{legacy.escape(played_on)}</div>
          <div class="hero-stage-note">当天所有比赛按系列赛分块展示，页面下方只保留当日各场比赛结果。</div>
          <div class="hero-stage-grid">
            <div class="hero-stage-metric"><span>系列赛</span><strong>{len(grouped_matches)}</strong><small>当天开赛系列赛</small></div>
            <div class="hero-stage-metric"><span>场次</span><strong>{len(day_matches)}</strong><small>当天完整对局</small></div>
            <div class="hero-stage-metric"><span>战队</span><strong>{total_team_count}</strong><small>已补录比赛战队</small></div>
            <div class="hero-stage-metric"><span>队员</span><strong>{total_player_count}</strong><small>已补录比赛人数</small></div>
          </div>
        </div>
      </div>
    </section>
    {ai_report_panel}
    {team_day_panel}
    {''.join(competition_sections)}
    """
    return layout(f"{played_on} 比赛日", body, ctx, alert=alert)


def get_match_day_legacy_page(ctx: RequestContext, played_on: str) -> str:
    return get_match_day_page_with_alert(ctx, played_on)


def handle_match_day_api(ctx: RequestContext, start_response, played_on: str):
    scope, error_message = _build_match_day_scope(ctx, played_on)
    if not scope:
        return start_response_json(
            start_response,
            "404 Not Found",
            {
                "error": error_message,
                "alert": form_value(ctx.query, "alert").strip(),
            },
        )
    return start_response_json(
        start_response,
        "200 OK",
        build_match_day_api_payload(ctx, played_on, scope),
    )


def handle_match_day(ctx: RequestContext, start_response, played_on: str):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", build_match_day_frontend_page(ctx, played_on))

    next_path = legacy.form_value(ctx.query, "next").strip() or "/dashboard"
    redirect_path = build_match_day_path(played_on, next_path)

    action = form_value(ctx.form, "action").strip()
    if action == "save_ai_daily_brief":
        admin_guard = require_admin(ctx, start_response)
        if admin_guard is not None:
            return admin_guard
        report_content = form_value(ctx.form, "report_content").strip()
        if not report_content:
            return redirect(start_response, append_alert_query(redirect_path, "日报正文不能为空。"))
        save_ai_match_day_report(
            played_on,
            report_content,
            "管理员手动编辑",
        )
        return redirect(start_response, append_alert_query(redirect_path, "AI 比赛日报已保存。"))

    if action != "generate_ai_daily_brief":
        return redirect(start_response, append_alert_query(redirect_path, "未识别的操作。"))

    existing_report = load_ai_match_day_report(played_on)
    if existing_report and not is_admin_user(ctx.current_user):
        return redirect(start_response, append_alert_query(redirect_path, "当前日报已生成，只有管理员可以重生成。"))

    if not is_valid_match_day(played_on):
        return redirect(start_response, append_alert_query(redirect_path, "比赛日期格式不正确。"))

    data = load_validated_data()
    day_matches = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (
                get_match_competition_name(item),
                (item.get("season") or "").strip(),
                item["round"],
                item["game_no"],
                item["match_id"],
            ),
        )
        if str(match.get("played_on") or "").strip() == played_on
    ]
    if not day_matches:
        return redirect(start_response, append_alert_query(redirect_path, "这一天还没有比赛记录。"))

    completed_day_matches, day_player_rows, day_team_rows = build_match_day_leaderboards(data, played_on)
    player_lookup = {player["player_id"]: player for player in data["players"]}
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    try:
        report_text, model = generate_ai_match_day_report(
            played_on,
            day_matches,
            day_team_rows,
            day_player_rows,
            player_lookup,
            team_lookup,
        )
        save_ai_match_day_report(played_on, report_text, model)
    except ValueError as exc:
        return redirect(start_response, append_alert_query(redirect_path, str(exc)))

    return redirect(start_response, append_alert_query(redirect_path, "AI 比赛日报已生成。"))


def get_teams_page(ctx: RequestContext) -> str:
    return legacy._legacy_get_teams_page_impl(ctx)


def _build_schedule_scope(ctx: RequestContext) -> tuple[dict[str, Any] | None, str]:
    data = load_validated_data()
    scope = resolve_catalog_scope(ctx, data)
    selected_competition = scope["selected_competition"]
    if not selected_competition:
        return None, "请先从赛事页进入具体赛事后，再查看全部场次。"

    selected_entry = scope["selected_entry"]
    selected_region = selected_entry["region_name"] if selected_entry else scope["selected_region"]
    selected_series_slug = (
        selected_entry["series_slug"] if selected_entry else scope["selected_series_slug"]
    )
    season_names = list_seasons(data, selected_competition)
    selected_season = get_selected_season(ctx, season_names)
    next_path = form_value(ctx.query, "next").strip() or build_scoped_path(
        "/competitions",
        selected_competition,
        selected_season,
        selected_region,
        selected_series_slug,
    )
    visible_rows = scope["filtered_rows"] or scope["region_rows"] or scope["competition_rows"]
    match_rows = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
            reverse=True,
        )
        if match_in_scope(match, selected_competition, selected_season)
    ]
    if not match_rows:
        return None, "当前系列赛和赛季下还没有比赛记录。"

    team_lookup = {team["team_id"]: team for team in data["teams"]}
    day_groups: dict[str, list[dict[str, Any]]] = {}
    for match in match_rows:
        day_groups.setdefault(match["played_on"], []).append(match)

    return (
        {
            "data": data,
            "scope": scope,
            "selected_competition": selected_competition,
            "selected_region": selected_region,
            "selected_series_slug": selected_series_slug,
            "season_names": season_names,
            "selected_season": selected_season,
            "next_path": next_path,
            "visible_rows": visible_rows,
            "match_rows": match_rows,
            "team_lookup": team_lookup,
            "day_groups": day_groups,
        },
        "",
    )


def _build_schedule_legacy_href(
    selected_competition: str,
    selected_season: str | None,
    next_path: str | None,
    selected_region: str | None,
    selected_series_slug: str | None,
) -> str:
    params: dict[str, str] = {}
    if selected_region:
        params["region"] = selected_region
    if selected_series_slug:
        params["series"] = selected_series_slug
    if selected_competition:
        params["competition"] = selected_competition
    if selected_season:
        params["season"] = selected_season
    if next_path:
        params["next"] = next_path
    query = urlencode(params)
    return f"/schedule/legacy?{query}" if query else "/schedule/legacy"


def _serialize_schedule_filters(
    selected_region: str | None,
    selected_series_slug: str | None,
    visible_rows: list[dict[str, Any]],
    selected_competition: str,
    season_names: list[str],
    selected_season: str | None,
) -> dict[str, list[dict[str, Any]]]:
    return {
        "competitions": [
            {
                "label": row["competition_name"],
                "href": build_schedule_path(
                    row["competition_name"],
                    None,
                    None,
                    selected_region,
                    selected_series_slug,
                ),
                "active": selected_competition == row["competition_name"],
            }
            for row in visible_rows
        ],
        "seasons": [
            {
                "label": season_name,
                "href": build_schedule_path(
                    selected_competition,
                    season_name,
                    None,
                    selected_region,
                    selected_series_slug,
                ),
                "selected": selected_season == season_name,
            }
            for season_name in season_names
        ],
    }


def _serialize_schedule_day_section(
    played_on: str,
    matches: list[dict[str, Any]],
    team_lookup: dict[str, dict[str, Any]],
    selected_competition: str,
    selected_season: str | None,
    selected_region: str | None,
    selected_series_slug: str | None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for match in matches:
        match_detail_path = (
            f"/matches/{match['match_id']}?next="
            f"{quote(build_schedule_path(selected_competition, selected_season, None, selected_region, selected_series_slug))}"
        )
        team_names = "、".join(
            sorted({team_lookup[entry["team_id"]]["name"] for entry in match["players"]})
        )
        rows.append(
            {
                "match_id": match["match_id"],
                "detail_href": match_detail_path,
                "season_name": match["season"],
                "stage_label": STAGE_OPTIONS.get(match["stage"], match["stage"]),
                "round_label": f"第 {match['round']} 轮",
                "group_label": str(match.get("group_label") or team_names or "未设置"),
                "table_label": match["table_label"],
                "format_label": match["format"],
            }
        )
    return {
        "played_on": played_on,
        "copy": f"当天共有 {len(matches)} 场比赛。点击日期可切换到该比赛日总览，点击单场编号可进入详情页。",
        "day_href": build_match_day_path(
            played_on,
            build_schedule_path(selected_competition, selected_season, None, selected_region, selected_series_slug),
        ),
        "rows": rows,
    }


def build_schedule_frontend_page(ctx: RequestContext) -> str:
    scope, error_message = _build_schedule_scope(ctx)
    if not scope:
        return get_competitions_page(ctx) if "请先从赛事页进入具体赛事" in error_message else layout(
            "赛事场次页",
            f'<div class="alert alert-secondary">{escape(error_message)}</div>',
            ctx,
        )

    if ctx.current_user:
        display_name = ctx.current_user.get("display_name") or ctx.current_user["username"]
        role_label = account_role_label(ctx.current_user)
        account_html = f"""
        <div class="shell-account">
          <span class="shell-account-label">{escape(display_name)} · {escape(role_label)}</span>
          <a class="shell-button shell-button-secondary" href="/profile">控制台</a>
          <form method="post" action="/logout" class="shell-inline-form">
            <button type="submit" class="shell-button shell-button-secondary">退出</button>
          </form>
        </div>
        """
    else:
        account_html = """
        <div class="shell-account">
          <a class="shell-button shell-button-secondary" href="/login">登录</a>
          <a class="shell-button shell-button-primary" href="/register">注册</a>
        </div>
        """

    bootstrap = json.dumps(
        {
            "apiEndpoint": "/api/schedule",
            "alert": form_value(ctx.query, "alert").strip(),
        },
        ensure_ascii=False,
    )
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#dceef7">
    <title>赛事场次页</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/competitions-app.css">
  </head>
  <body class="competitions-app-shell">
    <div class="shell-backdrop"></div>
    <header class="shell-header">
      <div class="shell-brand">
        <a class="shell-brand-link" href="/schedule">赛事场次页</a>
        <span class="shell-brand-copy">Schedule Frontend · API Driven</span>
      </div>
      <nav class="shell-nav" aria-label="主导航">
        <a class="shell-nav-link" href="/dashboard">首页</a>
        <a class="shell-nav-link" href="/competitions">比赛页面</a>
        <a class="shell-nav-link is-active" href="/schedule">全部场次</a>
      </nav>
      {account_html}
    </header>
    <main id="schedule-app" class="competitions-app-root" aria-live="polite">
      <section class="competitions-loading-shell">
        <div class="competitions-loading-kicker">Loading Schedule</div>
        <h1>正在加载赛事场次页</h1>
        <p>新前端会通过独立 API 拉取赛季下的比赛日和场次列表。</p>
      </section>
    </main>
    <script>window.__WEREWOLF_SCHEDULE_BOOTSTRAP__ = {bootstrap};</script>
    <script src="/assets/schedule-app.js" defer></script>
  </body>
</html>
"""


def build_schedule_api_payload(
    ctx: RequestContext,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if scope is None:
        scope, error_message = _build_schedule_scope(ctx)
    else:
        error_message = ""
    if not scope:
        return {"error": error_message, "alert": form_value(ctx.query, "alert").strip()}

    selected_competition = scope["selected_competition"]
    selected_region = scope["selected_region"]
    selected_series_slug = scope["selected_series_slug"]
    selected_season = scope["selected_season"]
    next_path = scope["next_path"]
    create_match_href = (
        "/matches/new?"
        + urlencode(
            {
                "competition": selected_competition,
                "season": selected_season or "",
                "next": build_schedule_path(
                    selected_competition,
                    selected_season,
                    None,
                    selected_region,
                    selected_series_slug,
                ),
            }
        )
        if can_manage_matches(ctx.current_user, scope["data"], selected_competition)
        else ""
    )
    total_team_count = len({entry["team_id"] for match in scope["match_rows"] for entry in match["players"]})
    total_player_count = len({entry["player_id"] for match in scope["match_rows"] for entry in match["players"]})
    day_groups = scope["day_groups"]
    return {
        "alert": form_value(ctx.query, "alert").strip(),
        "hero": {
            "title": f"{selected_competition} · 全部场次",
            "copy": "这里集中展示该系列赛当前赛季的所有场次。你可以按日期查看，也可以直接点击某一场进入详情页。",
            "selected_season": selected_season or selected_competition,
        },
        "filters": _serialize_schedule_filters(
            selected_region,
            selected_series_slug,
            scope["visible_rows"],
            selected_competition,
            scope["season_names"],
            selected_season,
        ),
        "metrics": [
            {"label": "比赛日", "value": str(len(day_groups)), "copy": "当前赛季涉及日期"},
            {"label": "比赛场次", "value": str(len(scope["match_rows"])), "copy": "当前赛季全部场次"},
            {"label": "参赛分组", "value": str(total_team_count), "copy": "当前赛季涉及战队"},
            {"label": "参赛队员", "value": str(total_player_count), "copy": "当前赛季上场"},
        ],
        "hero_side": {
            "season_title": selected_season or selected_competition,
            "first_day": min(day_groups.keys()),
            "last_day": max(day_groups.keys()),
            "match_count": str(len(scope["match_rows"])),
            "day_count": str(len(day_groups)),
        },
        "actions": {
            "back_href": next_path,
            "create_match_href": create_match_href,
        },
        "days": [
            _serialize_schedule_day_section(
                played_on,
                matches,
                scope["team_lookup"],
                selected_competition,
                selected_season,
                selected_region,
                selected_series_slug,
            )
            for played_on, matches in day_groups.items()
        ],
        "legacy_href": _build_schedule_legacy_href(
            selected_competition,
            selected_season,
            next_path,
            selected_region,
            selected_series_slug,
        ),
    }


def get_schedule_legacy_page(ctx: RequestContext) -> str:
    data = load_validated_data()
    scope = resolve_catalog_scope(ctx, data)
    competition_names = scope["competition_names"]
    selected_competition = scope["selected_competition"]
    if not selected_competition:
        return get_competitions_page(ctx)

    selected_entry = scope["selected_entry"]
    selected_region = selected_entry["region_name"] if selected_entry else scope["selected_region"]
    selected_series_slug = (
        selected_entry["series_slug"] if selected_entry else scope["selected_series_slug"]
    )
    season_names = list_seasons(data, selected_competition)
    selected_season = get_selected_season(ctx, season_names)
    next_path = form_value(ctx.query, "next").strip() or build_scoped_path(
        "/competitions",
        selected_competition,
        selected_season,
        selected_region,
        selected_series_slug,
    )
    competition_switcher = build_competition_switcher(
        "/schedule/legacy",
        [row["competition_name"] for row in (scope["filtered_rows"] or scope["region_rows"] or scope["competition_rows"])],
        selected_competition,
        tone="light",
        all_label="返回赛事总览",
        region_name=selected_region,
        series_slug=selected_series_slug,
    )
    season_switcher = build_season_switcher(
        "/schedule/legacy",
        selected_competition,
        season_names,
        selected_season,
        tone="light",
        region_name=selected_region,
        series_slug=selected_series_slug,
    )
    season_switcher_html = (
        f'<div class="hero-switchers mt-3">{season_switcher}</div>' if season_switcher else ""
    )

    match_rows = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
            reverse=True,
        )
        if match_in_scope(match, selected_competition, selected_season)
    ]
    if not match_rows:
        return layout(
            "赛事场次页",
            '<div class="alert alert-secondary">当前系列赛和赛季下还没有比赛记录。</div>',
            ctx,
        )

    team_lookup = {team["team_id"]: team for team in data["teams"]}
    day_groups: dict[str, list[dict[str, Any]]] = {}
    for match in match_rows:
        day_groups.setdefault(match["played_on"], []).append(match)

    create_match_button = ""
    if can_manage_matches(ctx.current_user, data, selected_competition):
        create_match_button = (
            f'<a class="btn btn-dark" href="/matches/new?'
            f'{urlencode({"competition": selected_competition, "season": selected_season or "", "next": build_schedule_path(selected_competition, selected_season, None, selected_region, selected_series_slug)})}">比赛管理</a>'
        )

    day_sections = []
    for played_on, matches in day_groups.items():
        rows = []
        for match in matches:
            match_detail_path = (
                f"/matches/{match['match_id']}?next="
                f"{quote(build_schedule_path(selected_competition, selected_season, None, selected_region, selected_series_slug))}"
            )
            team_names = "、".join(
                sorted({team_lookup[entry["team_id"]]["name"] for entry in match["players"]})
            )
            rows.append(
                f"""
                <tr>
                  <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(match_detail_path)}">{escape(match['match_id'])}</a></td>
                  <td>{escape(match['season'])}</td>
                  <td>{escape(STAGE_OPTIONS.get(match['stage'], match['stage']))}</td>
                  <td>第 {match['round']} 轮</td>
                  <td>{escape(str(match.get('group_label') or team_names or '未设置'))}</td>
                  <td>{escape(match['table_label'])}</td>
                  <td>{escape(match['format'])}</td>
                  <td><a class="btn btn-sm btn-outline-dark" href="{escape(match_detail_path)}">查看详情</a></td>
                </tr>
                """
            )
        day_sections.append(
            f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
                <div>
                  <h2 class="section-title mb-2"><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(build_match_day_path(played_on, build_schedule_path(selected_competition, selected_season, None, selected_region, selected_series_slug)))}">{escape(played_on)}</a></h2>
                  <p class="section-copy mb-0">当天共有 {len(matches)} 场比赛。点击日期可切换到该比赛日总览，点击单场编号可进入详情页。</p>
                </div>
              </div>
              <div class="table-responsive">
                <table class="table align-middle">
                  <thead>
                    <tr>
                      <th>编号</th>
                      <th>赛季</th>
                      <th>阶段</th>
                      <th>轮次</th>
                      <th>参赛分组</th>
                      <th>房间</th>
                      <th>板型</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {''.join(rows)}
                  </tbody>
                </table>
              </div>
            </section>
            """
        )

    total_team_count = len({entry["team_id"] for match in match_rows for entry in match["players"]})
    total_player_count = len({entry["player_id"] for match in match_rows for entry in match["players"]})
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">赛事场次页</div>
          <h1 class="hero-title mb-3">{escape(selected_competition)} · 全部场次</h1>
          <p class="hero-copy mb-0">这里集中展示该系列赛当前赛季的所有场次。你可以按日期查看，也可以直接点击某一场进入详情页。</p>
          <div class="hero-switchers mt-4">{competition_switcher}</div>
          {season_switcher_html}
          <div class="d-flex flex-wrap gap-2 mt-4">
            <a class="btn btn-outline-dark" href="{escape(next_path)}">返回赛事页</a>
            {create_match_button}
          </div>
          <div class="hero-kpis">
            <div class="hero-pill"><span>比赛日</span><strong>{len(day_groups)}</strong><small>当前赛季涉及日期</small></div>
            <div class="hero-pill"><span>比赛场次</span><strong>{len(match_rows)}</strong><small>当前赛季全部场次</small></div>
            <div class="hero-pill"><span>参赛分组</span><strong>{total_team_count}</strong><small>当前赛季涉及战队</small></div>
            <div class="hero-pill"><span>参赛队员</span><strong>{total_player_count}</strong><small>当前赛季上场</small></div>
          </div>
        </div>
        <div class="hero-stage-card">
          <div class="official-mark">Schedule Board</div>
          <div class="hero-stage-label">All Matches</div>
          <div class="hero-stage-title">{escape(selected_season or selected_competition)}</div>
          <div class="hero-stage-note">这个页面只保留场次视角，不混入战队入口，适合连续查看该比赛全部赛程。</div>
          <div class="hero-stage-grid">
            <div class="hero-stage-metric"><span>首个比赛日</span><strong>{escape(min(day_groups.keys()))}</strong><small>当前赛季起始</small></div>
            <div class="hero-stage-metric"><span>最后比赛日</span><strong>{escape(max(day_groups.keys()))}</strong><small>当前赛季截止</small></div>
          </div>
        </div>
      </div>
    </section>
    {''.join(day_sections)}
    """
    return layout("赛事场次页", body, ctx)


def get_schedule_page(ctx: RequestContext) -> str:
    return build_schedule_frontend_page(ctx)


def handle_schedule_api(ctx: RequestContext, start_response):
    scope, error_message = _build_schedule_scope(ctx)
    if not scope:
        return start_response_json(
            start_response,
            "404 Not Found",
            {"error": error_message, "alert": form_value(ctx.query, "alert").strip()},
        )
    return start_response_json(start_response, "200 OK", build_schedule_api_payload(ctx, scope))


def handle_competitions(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(
            start_response,
            "200 OK",
            build_competitions_frontend_page(ctx),
        )

    action = form_value(ctx.form, "action").strip()
    if action == "save_ai_season_summary":
        admin_guard = require_admin(ctx, start_response)
        if admin_guard is not None:
            return admin_guard

        competition_name = form_value(ctx.form, "competition_name").strip()
        season_name = form_value(ctx.form, "season_name").strip()
        region_name = form_value(ctx.form, "region_name").strip()
        series_slug = form_value(ctx.form, "series_slug").strip()
        summary_content = form_value(ctx.form, "summary_content").strip()
        redirect_path = build_scoped_path(
            "/competitions",
            competition_name,
            season_name,
            region_name,
            series_slug,
        )
        if not summary_content:
            return redirect(start_response, append_alert_query(redirect_path, "赛季总结正文不能为空。"))
        save_ai_season_summary(
            competition_name,
            season_name,
            summary_content,
            "管理员手动编辑",
        )
        return redirect(start_response, append_alert_query(redirect_path, "AI 赛季总结已保存。"))

    if action == "generate_ai_season_summary":
        competition_name = form_value(ctx.form, "competition_name").strip()
        season_name = form_value(ctx.form, "season_name").strip()
        region_name = form_value(ctx.form, "region_name").strip()
        series_slug = form_value(ctx.form, "series_slug").strip()
        redirect_path = build_scoped_path(
            "/competitions",
            competition_name,
            season_name,
            region_name,
            series_slug,
        )
        if not competition_name or not season_name:
            return redirect(
                start_response,
                append_alert_query(redirect_path, "请先进入具体赛季页，再生成 AI 赛季总结。"),
            )
        existing_summary = load_ai_season_summary(competition_name, season_name)
        if existing_summary and not is_admin_user(ctx.current_user):
            return redirect(
                start_response,
                append_alert_query(redirect_path, "当前赛季总结已生成，只有管理员可以重生成。"),
            )

        data = load_validated_data()
        match_rows = [
            match
            for match in sorted(
                data["matches"],
                key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
            )
            if match_in_scope(match, competition_name, season_name)
        ]
        if not match_rows:
            return redirect(
                start_response,
                append_alert_query(redirect_path, "当前赛季还没有可用于总结的比赛数据。"),
            )

        played_match_rows = [
            match
            for match in match_rows
            if is_match_counted_as_played(match)
        ]
        stats_data = {
            "teams": data["teams"],
            "players": data["players"],
            "matches": played_match_rows,
        }
        team_rows = [
            row for row in build_team_rows(stats_data, competition_name, season_name)
            if row["matches_represented"] > 0
        ]
        player_rows = [
            row for row in build_player_rows(stats_data, competition_name, season_name)
            if row["games_played"] > 0
        ]
        stage_team_rows = build_stage_team_rows(data, competition_name, season_name)
        mvp_rows = build_player_mvp_rows(data, competition_name, season_name)
        team_rows.sort(key=lambda row: (row.get("points_rank", 9999), -row["points_earned_total"], row["name"]))
        player_rows.sort(key=lambda row: (row["rank"], -row["points_earned_total"], row["display_name"]))
        try:
            report_text, model = generate_ai_season_summary(
                competition_name,
                season_name,
                match_rows,
                team_rows,
                player_rows,
                stage_team_rows,
                mvp_rows,
            )
            save_ai_season_summary(competition_name, season_name, report_text, model)
        except ValueError as exc:
            return redirect(start_response, append_alert_query(redirect_path, str(exc)))

        return redirect(start_response, append_alert_query(redirect_path, "AI 赛季总结已生成。"))

    return start_response_html(
        start_response,
        "405 Method Not Allowed",
        layout("请求无效", '<div class="alert alert-danger">赛事页不再提供战队报名操作。</div>', ctx),
    )


def summarize_team_match(team_id: str, match: dict[str, Any], team_lookup: dict[str, Any]) -> dict[str, Any]:
    team_score = 0.0
    opponents: dict[str, float] = {}
    for participant in match["players"]:
        if participant["team_id"] == team_id:
            team_score += float(participant["points_earned"])
        else:
            opponents.setdefault(participant["team_id"], 0.0)
            opponents[participant["team_id"]] += float(participant["points_earned"])

    opponent_names = "、".join(team_lookup[opponent_id]["name"] for opponent_id in opponents)
    opponent_score = sum(opponents.values())
    winning_camp = str(match.get("winning_camp") or "").strip()
    winning_camp_label = {
        "villagers": "好人胜利",
        "werewolves": "狼人胜利",
        "third_party": "第三方胜利",
        "draw": "平局",
    }.get(winning_camp, CAMP_OPTIONS.get(winning_camp, winning_camp))
    return {
        "match_id": match["match_id"],
        "competition_name": get_match_competition_name(match),
        "season": match["season"],
        "stage": STAGE_OPTIONS.get(match["stage"], match["stage"]),
        "round": match["round"],
        "game_no": match["game_no"],
        "played_on": match["played_on"],
        "table_label": match["table_label"],
        "format": match["format"],
        "duration_minutes": match["duration_minutes"],
        "winning_camp": winning_camp_label,
        "team_score": round(team_score, 2),
        "opponent_score": round(opponent_score, 2),
        "opponents": opponent_names or "无",
        "notes": match["notes"],
    }


def build_match_next_path(match: dict[str, Any]) -> str:
    return build_scoped_path(
        "/competitions",
        get_match_competition_name(match),
        (match.get("season") or "").strip() or None,
    )


def list_match_days(data: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(match.get("played_on") or "").strip()
            for match in data["matches"]
            if str(match.get("played_on") or "").strip() and is_match_counted_as_played(match)
        },
        reverse=True,
    )


def build_match_day_path(played_on: str, next_path: str | None = None) -> str:
    base_path = f"/days/{played_on}"
    if not next_path:
        return base_path
    return f"{base_path}?{legacy.urlencode({'next': next_path})}"


def build_schedule_path(
    competition_name: str | None = None,
    season_name: str | None = None,
    next_path: str | None = None,
    region_name: str | None = None,
    series_slug: str | None = None,
) -> str:
    params: dict[str, str] = {}
    if region_name:
        params["region"] = region_name
    if series_slug:
        params["series"] = series_slug
    if competition_name:
        params["competition"] = competition_name
    if season_name:
        params["season"] = season_name
    if next_path:
        params["next"] = next_path
    query = legacy.urlencode(params)
    return f"/schedule?{query}" if query else "/schedule"


def is_valid_match_day(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False
