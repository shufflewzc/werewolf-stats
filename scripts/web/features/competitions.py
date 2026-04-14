from __future__ import annotations

import calendar
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
can_access_series_management = legacy.can_access_series_management
can_manage_competition_catalog = legacy.can_manage_competition_catalog
can_manage_competition_seasons = legacy.can_manage_competition_seasons
can_manage_matches = legacy.can_manage_matches
can_manage_team = legacy.can_manage_team
escape = legacy.escape
format_datetime_local_label = legacy.format_datetime_local_label
format_pct = legacy.format_pct
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
sort_match_days_by_relevance = legacy.sort_match_days_by_relevance
load_season_catalog = legacy.load_season_catalog
load_series_catalog = legacy.load_series_catalog
load_validated_data = legacy.load_validated_data
match_in_scope = legacy.match_in_scope
quote = legacy.quote
redirect = legacy.redirect
resolve_catalog_scope = legacy.resolve_catalog_scope
require_login = legacy.require_login
save_season_catalog = legacy.save_season_catalog
season_status_label = legacy.season_status_label
start_response_html = legacy.start_response_html
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
    current_player = get_user_player(data, ctx.current_user)
    can_manage_selected_match_scope = bool(selected_competition and can_manage_matches(ctx.current_user, data, selected_competition))
    can_edit_selected_competition = bool(selected_competition and can_manage_competition_catalog(ctx.current_user, data, selected_competition))
    can_manage_selected_seasons = bool(selected_competition and can_manage_competition_seasons(ctx.current_user, data, selected_competition))
    _, current_user_team = get_user_captained_team_for_scope(data, ctx.current_user, selected_competition, selected_season) if selected_competition and selected_season else (None, None)
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
    registered_team_ids = season_entry.get("registered_team_ids", []) if season_entry else []
    registration_form_html = ""
    season_status_text = "待配置"
    season_period_text = "请先设置赛季起止时间"
    season_note_text = "当前赛季还没有配置档期，暂时无法开放战队报名。"
    if season_entry:
        season_status_text = season_status_label(season_entry)
        season_period_text = f"{format_datetime_local_label(season_entry.get('start_at', ''))} - {format_datetime_local_label(season_entry.get('end_at', ''))}"
        season_note_text = season_entry.get("notes") or "可以在这里查看本赛季的进行状态，并管理赛季报名。"
        if current_user_team and can_manage_team(ctx, current_user_team, current_player):
            is_registered = current_user_team["team_id"] in registered_team_ids
            action_name = "cancel_team_registration" if is_registered else "register_team_for_season"
            action_label = "取消报名我的战队" if is_registered else "报名我的战队"
            helper_text = f"当前账号可为 {current_user_team['name']} 执行报名操作。" if get_season_status(season_entry) == "ongoing" else "只有进行中的赛季才开放战队报名。"
            registration_form_html = f"""<form method="post" action="/competitions"><input type="hidden" name="action" value="{action_name}"><input type="hidden" name="competition_name" value="{escape(selected_competition)}"><input type="hidden" name="season_name" value="{escape(selected_season or '')}"><input type="hidden" name="team_id" value="{escape(current_user_team['team_id'])}"><input type="hidden" name="next" value="{escape(current_competition_path)}"><div class="small text-secondary mb-3">{escape(helper_text)}</div><button type="submit" class="btn btn-dark"{'' if get_season_status(season_entry) == 'ongoing' else ' disabled'}>{escape(action_label)}</button></form>"""
        elif is_admin_user(ctx.current_user):
            team_options_html = "".join(f'<option value="{escape(team["team_id"])}">{escape(team["name"])}</option>' for team in data["teams"] if team_matches_scope(team, selected_competition, selected_season or ""))
            registration_form_html = f"""<form method="post" action="/competitions"><input type="hidden" name="action" value="register_team_for_season"><input type="hidden" name="competition_name" value="{escape(selected_competition)}"><input type="hidden" name="season_name" value="{escape(selected_season or '')}"><input type="hidden" name="next" value="{escape(current_competition_path)}"><div class="small text-secondary mb-3">管理员可代任意战队提交报名。</div><div class="d-flex flex-column gap-3"><select class="form-select" name="team_id">{team_options_html}</select><button type="submit" class="btn btn-dark"{'' if get_season_status(season_entry) == 'ongoing' else ' disabled'}>为所选战队报名</button></div></form>"""
    season_registration_panel = ""
    if selected_season:
        season_registration_panel = f"""<section class="panel shadow-sm p-3 p-lg-4 mb-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h2 class="section-title mb-2">赛季档期与战队报名</h2><p class="section-copy mb-0">当前查看的是 {escape(selected_season)}。赛事负责人可以维护赛季起止时间，具备战队管理权限的账号、已认领战队的负责人或管理员可以为自己的战队报名正在进行中的赛季。</p></div><div class="d-flex flex-wrap gap-2">{season_manage_button}</div></div><div class="row g-3"><div class="col-12 col-lg-6"><div class="team-link-card shadow-sm p-4 h-100"><div class="card-kicker mb-2">赛季状态</div><h3 class="h5 mb-2">{escape(season_status_text)}</h3><div class="small-muted mb-2">起止时间 {escape(season_period_text)}</div><p class="section-copy mb-0">{escape(season_note_text)}</p></div></div><div class="col-12 col-lg-6"><div class="team-link-card shadow-sm p-4 h-100"><div class="card-kicker mb-2">我的已认领战队</div><h3 class="h5 mb-2">{escape(current_user_team['name']) if current_user_team else '暂无已认领战队'}</h3><div class="small-muted mb-2">{'认领负责人或管理员可执行报名' if current_user_team else ('管理员可代战队报名' if is_admin_user(ctx.current_user) else '当前账号在本赛季还没有已认领战队')}</div>{registration_form_html or '<div class="section-copy">当前账号没有可用于报名的战队，或你还不是该战队的认领负责人。</div>'}</div></div></div></section>"""
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
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4"><div class="hero-layout"><div><div class="eyebrow mb-3">{escape(page_badge)}</div><h1 class="hero-title mb-3">{escape(hero_title)}</h1><p class="hero-copy mb-0">{escape(hero_intro)}</p>{region_switcher_html}{series_switcher_html}<div class="hero-switchers mt-3">{competition_switcher}</div>{season_switcher_html}<div class="hero-kpis"><div class="hero-pill"><span>参赛战队</span><strong>{len(team_rows)}</strong><small>{escape(selected_season or '当前赛季')} 真实参赛</small></div><div class="hero-pill"><span>参赛队员</span><strong>{player_count}</strong><small>{escape(selected_season or '当前赛季')} 已上场</small></div><div class="hero-pill"><span>赛季场次</span><strong>{len(match_rows)}</strong><small>{escape(scope_label)} 完整赛程</small></div></div></div><div class="hero-stage-card"><div class="official-mark">Event Sheet</div><div class="hero-stage-label">Season Overview</div><div class="hero-stage-title">{escape(scope_label)}</div><div class="hero-stage-note">{escape(hero_note)}</div><div class="hero-stage-grid"><div class="hero-stage-metric"><span>最近比赛日</span><strong>{escape(latest_played_on)}</strong><small>{escape(selected_season or (' / '.join(competition_meta['seasons'][:2]) if competition_meta and competition_meta['seasons'] else '赛季待录入'))}</small></div><div class="hero-stage-metric"><span>参赛战队</span><strong>{len(team_rows)}</strong><small>该赛季参赛战队</small></div><div class="hero-stage-metric"><span>参赛队员</span><strong>{player_count}</strong><small>该赛季实际出场</small></div><div class="hero-stage-metric"><span>赛季场次</span><strong>{len(match_rows)}</strong><small>该赛季完整赛程</small></div></div></div></div></section>
    {season_registration_panel}
    {leaderboard_sections}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h2 class="section-title mb-2">该赛季战队入口</h2><p class="section-copy mb-0">这里只保留当前赛季的战队名称入口，点进后继续看同一赛季口径下的战队详情。</p></div><div class="d-flex flex-wrap gap-2">{create_match_button}{edit_competition_button}{series_topic_button}{schedule_page_button}<a class="btn btn-outline-dark" href="{escape(build_scoped_path('/competitions', None, None, selected_region, selected_series_slug))}">返回地区赛事列表</a></div></div><div class="d-flex flex-wrap gap-2">{team_links_html or '<div class="alert alert-secondary mb-0 w-100">当前赛季还没有战队数据。</div>'}</div></section>
    <section class="panel shadow-sm p-3 p-lg-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h2 class="section-title mb-2">该赛季完整赛程</h2><p class="section-copy mb-0">按日历展示当前赛季的比赛日期；有比赛的日期会高亮显示，点击即可进入当天比赛结果页。</p></div></div>{season_schedule_calendar}</section>
    """
    return layout(scope_label, body, ctx, alert=alert)


def get_series_page(ctx: RequestContext, series_slug: str) -> str:
    data = load_validated_data()
    catalog = load_series_catalog(data)
    series_entries = get_series_entries_by_slug(catalog, series_slug)
    if not series_entries:
        return layout("未找到系列赛", '<div class="alert alert-danger">没有找到对应的系列赛专题页。</div>', ctx)
    competition_rows = build_competition_catalog_rows(data, catalog)
    series_rows = [row for row in competition_rows if row["series_slug"] == series_slug]
    if not series_rows:
        return layout("未找到系列赛", '<div class="alert alert-danger">该系列赛还没有关联任何地区赛事。</div>', ctx)
    allowed_competitions = {row["competition_name"] for row in series_rows}
    series_data = build_filtered_data(data, allowed_competitions)
    season_names = list_seasons(series_data, series_slug=series_slug)
    selected_season = get_selected_season(ctx, season_names)
    filtered_matches = [match for match in sorted(series_data["matches"], key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]), reverse=True) if not selected_season or (match.get("season") or "").strip() == selected_season]
    season_switcher = build_series_season_switcher(series_slug, season_names, selected_season)
    season_switcher_html = f'<div class="hero-switchers mt-4">{season_switcher}</div>' if season_switcher else ""
    region_names = "、".join(sorted({row["region_name"] for row in series_rows}))
    latest_played_on = get_scheduled_match_day_label(
        filtered_matches,
        legacy.china_today_label(),
    )
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


def get_match_day_page(ctx: RequestContext, played_on: str) -> str:
    if not is_valid_match_day(played_on):
        return layout("未找到比赛日", '<div class="alert alert-danger">比赛日期格式不正确。</div>', ctx)

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
        return layout("未找到比赛日", '<div class="alert alert-danger">这一天还没有比赛记录。</div>', ctx)

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
    {''.join(competition_sections)}
    """
    return layout(f"{played_on} 比赛日", body, ctx)


def get_teams_page(ctx: RequestContext) -> str:
    return legacy._legacy_get_teams_page_impl(ctx)


def handle_competitions(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_competitions_page(ctx))

    guard = require_login(ctx, start_response)
    if guard is not None:
        return guard

    action = legacy.form_value(ctx.form, "action").strip()
    if action not in {"register_team_for_season", "cancel_team_registration"}:
        return start_response_html(
            start_response,
            "405 Method Not Allowed",
            layout("请求无效", '<div class="alert alert-danger">未识别的赛事报名操作。</div>', ctx),
        )

    data = load_validated_data()
    season_catalog = load_season_catalog(data)
    series_catalog = load_series_catalog(data)
    current_player = get_user_player(data, ctx.current_user)
    next_path = legacy.form_value(ctx.form, "next").strip() or "/competitions"
    competition_name = legacy.form_value(ctx.form, "competition_name").strip()
    season_name = legacy.form_value(ctx.form, "season_name").strip()
    team_id = legacy.form_value(ctx.form, "team_id").strip()
    render_ctx = RequestContext(
        method="GET",
        path="/competitions",
        query={
            **({"competition": [competition_name]} if competition_name else {}),
            **({"season": [season_name]} if season_name else {}),
        },
        form={},
        files={},
        current_user=ctx.current_user,
        now_label=ctx.now_label,
    )
    team = legacy.get_team_by_id(data, team_id)
    if not team:
        return start_response_html(
            start_response,
            "200 OK",
            get_competitions_page(render_ctx, alert="没有找到要报名的战队。"),
        )
    if not legacy.team_matches_scope(team, competition_name, season_name):
        return start_response_html(
            start_response,
            "200 OK",
            get_competitions_page(render_ctx, alert="战队只能报名自己所属赛事赛季。"),
        )
    if not legacy.can_manage_team(ctx, team, current_player):
        return start_response_html(
            start_response,
            "403 Forbidden",
            layout("没有权限", '<div class="alert alert-danger">只有具备战队管理权限的账号、已认领该战队的负责人或管理员可以为战队报名赛季。</div>', ctx),
        )
    series_slug = legacy.build_series_context_from_competition(
        competition_name,
        series_catalog,
    )["series_slug"]
    season_entry = get_season_entry(
        season_catalog,
        series_slug,
        season_name,
        competition_name=competition_name,
    )
    if not season_entry:
        return start_response_html(
            start_response,
            "200 OK",
            get_competitions_page(render_ctx, alert="当前赛季还没有配置起止时间，请先让赛事负责人完成赛季设置。"),
        )
    if get_season_status(season_entry) != "ongoing":
        return start_response_html(
            start_response,
            "200 OK",
            get_competitions_page(render_ctx, alert="只有进行中的赛季才允许战队报名。"),
        )

    registered_team_ids = [
        registered_team_id
        for registered_team_id in season_entry.get("registered_team_ids", [])
        if registered_team_id != team_id
    ]
    if action == "register_team_for_season":
        registered_team_ids.append(team_id)

    updated_catalog = []
    for item in season_catalog:
        if (
            item["series_slug"] == series_slug
            and item.get("competition_name", "") == competition_name
            and item["season_name"] == season_name
        ):
            updated_catalog.append({**item, "registered_team_ids": registered_team_ids})
        else:
            updated_catalog.append(item)
    save_season_catalog(updated_catalog)
    return redirect(start_response, next_path)


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
        "winning_camp": CAMP_OPTIONS.get(match["winning_camp"], match["winning_camp"]),
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
