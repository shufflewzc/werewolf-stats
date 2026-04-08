from __future__ import annotations

from datetime import datetime

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
get_season_entry = legacy.get_season_entry
get_season_status = legacy.get_season_status
get_series_entry_by_competition = legacy.get_series_entry_by_competition
get_user_captained_team_for_scope = legacy.get_user_captained_team_for_scope
get_user_player = legacy.get_user_player
is_admin_user = legacy.is_admin_user
layout = legacy.layout
list_seasons = legacy.list_seasons
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
        key=lambda row: (row["latest_played_on"], row["competition_name"]),
        default=None,
    )
    region_switcher = build_region_switcher("/competitions", scope["region_names"], selected_region, selected_series_slug)
    series_switcher = build_series_switcher("/competitions", series_rows, selected_region, selected_series_slug)

    if not selected_competition:
        cards = []
        for row in filtered_rows or region_rows:
            topic_path = build_series_topic_path(row["series_slug"])
            competition_path = build_scoped_path("/competitions", row["competition_name"], None, row["region_name"], row["series_slug"])
            card_summary = row["summary"] or f"{row['region_name']}赛区的 {row['series_name']} 官方赛事页。"
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
        <section class="hero p-4 p-md-5 shadow-lg mb-4"><div class="hero-layout"><div><div class="eyebrow mb-3">地区赛事站点</div><h1 class="hero-title mb-3">{escape(selected_region or DEFAULT_REGION_NAME)}赛区官方入口</h1><p class="hero-copy mb-0">先选择地区，再筛选系列赛。每张卡片都同时提供系列赛专题页和该地区的独立赛事站点，方便按赛区管理和按品牌汇总浏览。</p><div class="hero-switchers mt-4">{region_switcher}</div><div class="hero-switchers mt-3">{series_switcher}</div><div class="hero-kpis"><div class="hero-pill"><span>地区站点</span><strong>{len(filtered_rows or region_rows)}</strong><small>{escape(selected_region or DEFAULT_REGION_NAME)} 当前可见</small></div><div class="hero-pill"><span>覆盖战队</span><strong>{total_team_count}</strong><small>当前地区口径</small></div><div class="hero-pill"><span>累计对局</span><strong>{total_match_count}</strong><small>当前筛选下完整赛程</small></div></div></div><div class="hero-stage-card"><div class="official-mark">Official Event Portal</div><div class="hero-stage-label">Featured Regional Event</div><div class="hero-stage-title">{escape(featured_name)}</div><div class="hero-stage-note">未登录时首页默认展示广州赛区；登录后会优先按账号所在地区进入对应赛区。进入单个地区赛事页后，你会继续看到该站自己的战队入口、赛程表和赛季切换，不会和其他地区混排。</div><div class="hero-stage-grid"><div class="hero-stage-metric"><span>最近比赛日</span><strong>{escape(featured_latest)}</strong><small>{escape(featured_seasons)}</small></div><div class="hero-stage-metric"><span>参赛战队</span><strong>{featured_competition['team_count'] if featured_competition else 0}</strong><small>当前特色赛事</small></div><div class="hero-stage-metric"><span>参赛队员</span><strong>{featured_competition['player_count'] if featured_competition else 0}</strong><small>当前特色赛事</small></div><div class="hero-stage-metric"><span>赛事场次</span><strong>{featured_competition['match_count'] if featured_competition else 0}</strong><small>当前特色地区站点</small></div></div></div></div></section>
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
    team_rows = [row for row in build_team_rows(data, selected_competition, selected_season) if row["matches_represented"] > 0]
    player_rows = [row for row in build_player_rows(data, selected_competition, selected_season) if row["games_played"] > 0]
    team_rows.sort(key=lambda row: (row.get("points_rank", 9999), -row["points_earned_total"], row["name"]))
    player_rows.sort(key=lambda row: (row["rank"], -row["points_earned_total"], row["display_name"]))
    match_rows = [match for match in sorted(data["matches"], key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]), reverse=True) if match_in_scope(match, selected_competition, selected_season)]
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
    create_match_button = f'<a class="btn btn-dark" href="/matches/new?{urlencode({"competition": selected_competition, "season": selected_season or "", "next": current_competition_path})}">录入今日比赛</a>' if can_manage_selected_match_scope else ""
    schedule_page_button = f'<a class="btn btn-outline-dark" href="{escape(build_schedule_path(selected_competition, selected_season, current_competition_path, selected_region, selected_series_slug))}">查看全部场次</a>'
    series_topic_button = f'<a class="btn btn-outline-dark" href="{escape(build_series_topic_path(competition_meta["series_slug"], selected_season))}">查看系列专题页</a>' if competition_meta else ""
    edit_competition_button = f'<a class="btn btn-outline-dark" href="{escape(build_series_manage_path(selected_competition, current_competition_path, None, "catalog"))}">编辑赛事页信息</a>' if can_edit_selected_competition else ""
    season_manage_button = f'<a class="btn btn-outline-dark" href="{escape(build_series_manage_path(selected_competition, current_competition_path, selected_season, "season"))}">管理赛季档期</a>' if can_manage_selected_seasons else ""
    latest_played_on = max((match["played_on"] for match in match_rows), default="待更新")
    registered_team_ids = season_entry.get("registered_team_ids", []) if season_entry else []
    registered_team_cards = [
        f"""<div class="col-12 col-md-6 col-xl-4"><a class="team-link-card shadow-sm p-3 h-100" href="{escape(build_scoped_path('/teams/' + registered_team_id, selected_competition, selected_season, selected_region, selected_series_slug))}"><div class="d-flex justify-content-between align-items-start gap-3"><div><div class="card-kicker mb-2">已报名战队</div><div class="fw-semibold">{escape(team_lookup[registered_team_id]['name'])}</div></div><span class="chip">查看战队</span></div></a></div>"""
        for registered_team_id in registered_team_ids
        if registered_team_id in team_lookup
    ]
    registration_form_html = ""
    season_status_text = "待配置"
    season_period_text = "请先设置赛季起止时间"
    season_note_text = "当前赛季还没有配置档期，暂时无法开放战队报名。"
    if season_entry:
        season_status_text = season_status_label(season_entry)
        season_period_text = f"{format_datetime_local_label(season_entry.get('start_at', ''))} - {format_datetime_local_label(season_entry.get('end_at', ''))}"
        season_note_text = season_entry.get("notes") or "可以在这里查看本赛季的进行状态，并管理已报名战队。"
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
        season_registration_panel = f"""<section class="panel shadow-sm p-3 p-lg-4 mb-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h2 class="section-title mb-2">赛季档期与战队报名</h2><p class="section-copy mb-0">当前查看的是 {escape(selected_season)}。赛事负责人可以维护赛季起止时间，具备战队管理权限的账号或战队队长可以为自己的战队报名正在进行中的赛季。</p></div><div class="d-flex flex-wrap gap-2">{season_manage_button}</div></div><div class="row g-3 mb-4"><div class="col-12 col-lg-4"><div class="team-link-card shadow-sm p-4 h-100"><div class="card-kicker mb-2">赛季状态</div><h3 class="h5 mb-2">{escape(season_status_text)}</h3><div class="small-muted mb-2">起止时间 {escape(season_period_text)}</div><p class="section-copy mb-0">{escape(season_note_text)}</p></div></div><div class="col-12 col-lg-4"><div class="team-link-card shadow-sm p-4 h-100"><div class="card-kicker mb-2">报名概览</div><h3 class="h5 mb-2">已报名 {len(registered_team_cards)} 支战队</h3><div class="small-muted mb-2">仅进行中的赛季允许新增或取消报名</div><p class="section-copy mb-0">报名成功后，战队会出现在本赛季赛事页的已报名名单中，方便赛程安排前统一确认参赛队伍。</p></div></div><div class="col-12 col-lg-4"><div class="team-link-card shadow-sm p-4 h-100"><div class="card-kicker mb-2">我的战队操作</div><h3 class="h5 mb-2">{escape(current_user_team['name']) if current_user_team else '未绑定战队'}</h3><div class="small-muted mb-2">{'队长或管理员可执行报名' if current_user_team else ('管理员可代战队报名' if is_admin_user(ctx.current_user) else '当前账号还没有加入战队')}</div>{registration_form_html or '<div class="section-copy">当前账号没有可用于报名的战队，或你不是该战队的队长。</div>'}</div></div></div><div class="row g-3">{''.join(registered_team_cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">当前赛季还没有战队报名。</div></div>'}</div></section>"""
    team_points_rows = [f"""<tr><td>{row.get('points_rank', '-')}</td><td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(build_scoped_path('/teams/' + row['team_id'], selected_competition, selected_season, selected_region, selected_series_slug))}">{escape(row['name'])}</a></td><td>{row['matches_represented']}</td><td>{row['player_count']}</td><td>{row['points_earned_total']:.2f}</td><td>{row.get('points_per_match', 0.0):.2f}</td><td>{format_pct(row['win_rate'])}</td></tr>""" for row in team_rows]
    player_points_rows = [f"""<tr><td>{row['rank']}</td><td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(build_scoped_path('/players/' + row['player_id'], selected_competition, selected_season, selected_region, selected_series_slug))}">{escape(row['display_name'])}</a></td><td>{escape(row['team_name'])}</td><td>{row['games_played']}</td><td>{escape(row['record'])}</td><td>{row['points_earned_total']:.2f}</td><td>{row['average_points']:.2f}</td><td>{format_pct(row['win_rate'])}</td></tr>""" for row in player_rows]
    team_cards = [f"""<div class="col-12 col-md-6"><a class="team-link-card shadow-sm p-4 h-100" href="{escape(build_scoped_path('/teams/' + row['team_id'], selected_competition, selected_season, selected_region, selected_series_slug))}"><div class="card-kicker mb-2">Team Access</div><h2 class="h4 mb-2">{escape(row['name'])}</h2><div class="small-muted mb-3">当前赛季积分榜第 {row.get('points_rank', row['rank'])} 名 · {row['player_count']} 名队员 · 对局 {row['matches_represented']} 场</div><div class="row g-3"><div class="col-4"><div class="small text-secondary">总积分</div><div class="fw-semibold">{row['points_earned_total']:.2f}</div></div><div class="col-4"><div class="small text-secondary">场均积分</div><div class="fw-semibold">{row.get('points_per_match', 0.0):.2f}</div></div><div class="col-4"><div class="small text-secondary">胜率</div><div class="fw-semibold">{format_pct(row['win_rate'])}</div></div></div></a></div>""" for row in team_rows]
    match_table_rows = []
    for match in match_rows:
        team_names = "、".join(sorted({team_lookup[entry["team_id"]]["name"] for entry in match["players"]}))
        match_detail_path = f"/matches/{match['match_id']}?next={quote(build_scoped_path('/competitions', selected_competition, selected_season, selected_region, selected_series_slug))}"
        day_path = build_match_day_path(match["played_on"], build_scoped_path("/competitions", selected_competition, selected_season, selected_region, selected_series_slug))
        match_table_rows.append(f"""<tr><td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(match_detail_path)}">{escape(match['match_id'])}</a></td><td>{escape(match['season'])}</td><td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(day_path)}">{escape(match['played_on'])}</a></td><td>{escape(STAGE_OPTIONS.get(match['stage'], match['stage']))}</td><td>第 {match['round']} 轮</td><td>第 {match['game_no']} 局</td><td>{escape(team_names)}</td><td>{escape(match['table_label'])}</td><td>{escape(match['format'])}</td><td><a class="btn btn-sm btn-outline-dark" href="{escape(match_detail_path)}">查看详情</a></td></tr>""")
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4"><div class="hero-layout"><div><div class="eyebrow mb-3">{escape(page_badge)}</div><h1 class="hero-title mb-3">{escape(hero_title)}</h1><p class="hero-copy mb-0">{escape(hero_intro)}</p>{region_switcher_html}{series_switcher_html}<div class="hero-switchers mt-3">{competition_switcher}</div>{season_switcher_html}<div class="hero-kpis"><div class="hero-pill"><span>参赛战队</span><strong>{len(team_rows)}</strong><small>{escape(selected_season or '当前赛季')} 真实参赛</small></div><div class="hero-pill"><span>参赛队员</span><strong>{player_count}</strong><small>{escape(selected_season or '当前赛季')} 已上场</small></div><div class="hero-pill"><span>赛季场次</span><strong>{len(match_rows)}</strong><small>{escape(scope_label)} 完整赛程</small></div></div></div><div class="hero-stage-card"><div class="official-mark">Official Event Sheet</div><div class="hero-stage-label">Season Overview</div><div class="hero-stage-title">{escape(scope_label)}</div><div class="hero-stage-note">{escape(hero_note)}</div><div class="hero-stage-grid"><div class="hero-stage-metric"><span>最近比赛日</span><strong>{escape(latest_played_on)}</strong><small>{escape(selected_season or (' / '.join(competition_meta['seasons'][:2]) if competition_meta and competition_meta['seasons'] else '赛季待录入'))}</small></div><div class="hero-stage-metric"><span>参赛战队</span><strong>{len(team_rows)}</strong><small>该赛季参赛战队</small></div><div class="hero-stage-metric"><span>参赛队员</span><strong>{player_count}</strong><small>该赛季实际出场</small></div><div class="hero-stage-metric"><span>赛季场次</span><strong>{len(match_rows)}</strong><small>该赛季完整赛程</small></div></div></div></div></section>
    {season_registration_panel}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h2 class="section-title mb-2">战队积分排行榜</h2><p class="section-copy mb-0">本榜单按当前赛事与赛季下所有上场队员的个人积分累计而成。也就是说，队员个人积分会直接计入战队赛季积分。</p></div></div><div class="table-responsive"><table class="table align-middle"><thead><tr><th>排名</th><th>战队</th><th>场次</th><th>上场队员</th><th>赛季总积分</th><th>场均积分</th><th>胜率</th></tr></thead><tbody>{''.join(team_points_rows) or '<tr><td colspan="7" class="text-secondary">当前赛季还没有战队积分数据。</td></tr>'}</tbody></table></div></section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h2 class="section-title mb-2">选手积分排行榜</h2><p class="section-copy mb-0">这里按当前赛事与赛季统计个人积分排名，方便直接查看这个小赛季下的选手表现。</p></div></div><div class="table-responsive"><table class="table align-middle"><thead><tr><th>排名</th><th>选手</th><th>战队</th><th>出场</th><th>战绩</th><th>赛季总积分</th><th>场均得分</th><th>胜率</th></tr></thead><tbody>{''.join(player_points_rows) or '<tr><td colspan="8" class="text-secondary">当前赛季还没有选手积分数据。</td></tr>'}</tbody></table></div></section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h2 class="section-title mb-2">该赛季战队入口</h2><p class="section-copy mb-0">这里只列出这个系列赛当前赛季真实参赛的战队，避免和其他赛季混在一起。点进战队卡片后，会继续看到同一赛季口径下的统计。</p></div><div class="d-flex flex-wrap gap-2">{create_match_button}{edit_competition_button}{series_topic_button}{schedule_page_button}<a class="btn btn-outline-dark" href="{escape(build_scoped_path('/competitions', None, None, selected_region, selected_series_slug))}">返回地区赛事列表</a></div></div><div class="row g-3 g-lg-4">{''.join(team_cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">当前赛季还没有战队数据。</div></div>'}</div></section>
    <section class="panel shadow-sm p-3 p-lg-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h2 class="section-title mb-2">该赛季完整赛程</h2><p class="section-copy mb-0">先在这里确认当前赛季的轮次和参赛战队，再从上面的战队入口继续查看更深一层的数据页面。</p></div></div><div class="table-responsive"><table class="table align-middle"><thead><tr><th>编号</th><th>赛季</th><th>日期</th><th>阶段</th><th>轮次</th><th>局次</th><th>参赛战队</th><th>桌号</th><th>板型</th><th>操作</th></tr></thead><tbody>{''.join(match_table_rows)}</tbody></table></div></section>
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
    filtered_series_data = {"teams": series_data["teams"], "players": series_data["players"], "matches": filtered_matches}
    player_rows = [row for row in build_player_rows(filtered_series_data) if row["games_played"] > 0]
    team_rows = [row for row in build_team_rows(filtered_series_data) if row["matches_represented"] > 0]
    team_rows.sort(key=lambda row: (row.get("points_rank", 9999), -row["points_earned_total"], row["name"]))
    player_rows.sort(key=lambda row: (row["rank"], -row["points_earned_total"], row["display_name"]))
    season_switcher = build_series_season_switcher(series_slug, season_names, selected_season)
    season_switcher_html = f'<div class="hero-switchers mt-4">{season_switcher}</div>' if season_switcher else ""
    region_names = "、".join(sorted({row["region_name"] for row in series_rows}))
    latest_played_on = max((match["played_on"] for match in filtered_matches), default="待更新")
    top_player = player_rows[0] if player_rows else None
    region_cards = []
    for row in series_rows:
        competition_path = build_scoped_path("/competitions", row["competition_name"], selected_season if selected_season in row["seasons"] else None, row["region_name"], row["series_slug"])
        region_cards.append(f"""<div class="col-12 col-lg-6"><a class="team-link-card shadow-sm p-4 h-100" href="{escape(competition_path)}"><div class="d-flex justify-content-between align-items-start gap-3"><div><div class="card-kicker mb-2">{escape(row['region_name'])} · Regional Event</div><h2 class="h4 mb-2">{escape(row['competition_name'])}</h2><div class="small-muted mb-2">赛季 {escape('、'.join(row['seasons'])) if row['seasons'] else '待录入'}</div><div class="small-muted">最近比赛日 {escape(row['latest_played_on'] or '待更新')}</div></div><span class="chip">进入地区赛事页</span></div><div class="row g-3 mt-2"><div class="col-4"><div class="small text-secondary">战队</div><div class="fw-semibold">{row['team_count']} 支</div></div><div class="col-4"><div class="small text-secondary">队员</div><div class="fw-semibold">{row['player_count']} 名</div></div><div class="col-4"><div class="small text-secondary">对局</div><div class="fw-semibold">{row['match_count']} 场</div></div></div></a></div>""")
    match_rows_html = []
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    for match in filtered_matches[:12]:
        detail_path = f"/matches/{match['match_id']}?next={quote(build_series_topic_path(series_slug, selected_season))}"
        competition_name = get_match_competition_name(match)
        series_entry = get_series_entry_by_competition(catalog, competition_name)
        region_name = series_entry["region_name"] if series_entry else DEFAULT_REGION_NAME
        team_names = "、".join(sorted({team_lookup[entry["team_id"]]["name"] for entry in match["players"]}))
        match_rows_html.append(f"""<tr><td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(detail_path)}">{escape(match['match_id'])}</a></td><td>{escape(region_name)}</td><td>{escape(competition_name)}</td><td>{escape(match['played_on'])}</td><td>{escape(STAGE_OPTIONS.get(match['stage'], match['stage']))}</td><td>第 {match['round']} 轮 / 第 {match['game_no']} 局</td><td>{escape(team_names)}</td><td><a class="btn btn-sm btn-outline-dark" href="{escape(detail_path)}">详情</a></td></tr>""")
    team_points_rows = [f"""<tr><td>{row.get('points_rank', '-')}</td><td>{escape(row['name'])}</td><td>{row['matches_represented']}</td><td>{row['player_count']}</td><td>{row['points_earned_total']:.2f}</td><td>{row.get('points_per_match', 0.0):.2f}</td><td>{format_pct(row['win_rate'])}</td></tr>""" for row in team_rows]
    leaderboard_rows = [f"""<tr><td>{row['rank']}</td><td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="/players/{row['player_id']}">{escape(row['display_name'])}</a></td><td>{escape(row['team_name'])}</td><td>{row['games_played']}</td><td>{escape(row['record'])}</td><td>{row['points_earned_total']:.2f}</td><td>{row['average_points']:.2f}</td><td>{format_pct(row['win_rate'])}</td></tr>""" for row in player_rows]
    manage_button = '<a class="btn btn-outline-dark" href="/series-manage">维护系列赛目录</a>' if can_access_series_management(ctx.current_user) else ""
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4"><div class="hero-layout"><div><div class="eyebrow mb-3">系列赛专题页</div><h1 class="hero-title mb-3">{escape(series_rows[0]['series_name'])}</h1><p class="hero-copy mb-0">这里会把同一系列赛在不同地区的比赛放到同一个专题页下浏览。你可以继续切换赛季，再进入任一地区赛事页查看该站独立数据。</p>{season_switcher_html}<div class="hero-kpis"><div class="hero-pill"><span>覆盖地区</span><strong>{len(series_rows)}</strong><small>{escape(region_names)}</small></div><div class="hero-pill"><span>专题场次</span><strong>{len(filtered_matches)}</strong><small>{escape(selected_season or '全部赛季')}</small></div><div class="hero-pill"><span>专题榜首</span><strong>{escape(top_player['display_name'] if top_player else '待更新')}</strong><small>{escape(top_player['team_name'] if top_player else '暂无数据')}</small></div></div></div><div class="hero-stage-card"><div class="official-mark">Cross Region Series</div><div class="hero-stage-label">Series Snapshot</div><div class="hero-stage-title">{escape(selected_season or '全部赛季')}</div><div class="hero-stage-note">这个专题页按系列赛品牌聚合，不按单一地区拆分。需要查看某个地区独立赛程时，可直接进入下面的地区赛事页。</div><div class="hero-stage-grid"><div class="hero-stage-metric"><span>最近比赛日</span><strong>{escape(latest_played_on)}</strong><small>{escape(region_names)}</small></div><div class="hero-stage-metric"><span>参赛战队</span><strong>{len(team_rows)}</strong><small>当前专题战队</small></div><div class="hero-stage-metric"><span>参赛队员</span><strong>{len(player_rows)}</strong><small>当前专题出场</small></div><div class="hero-stage-metric"><span>地区站点</span><strong>{len(series_rows)}</strong><small>系列赛覆盖地区</small></div></div></div></div></section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h2 class="section-title mb-2">地区赛事页</h2><p class="section-copy mb-0">同一系列赛的不同地区站点会一起列在这里，点击后可进入各地区自己的赛季页与战队页。</p></div><div class="d-flex flex-wrap gap-2">{manage_button}<a class="btn btn-outline-dark" href="{escape(build_scoped_path('/dashboard', None, None, DEFAULT_REGION_NAME, None))}">返回首页</a></div></div><div class="row g-3 g-lg-4">{''.join(region_cards)}</div></section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h2 class="section-title mb-2">专题战队积分排行榜</h2><p class="section-copy mb-0">这里会把同一系列赛下不同地区、同一赛季的战队积分合并统计，形成该系列赛赛季口径的官方战队积分榜。</p></div></div><div class="table-responsive"><table class="table align-middle"><thead><tr><th>排名</th><th>战队</th><th>场次</th><th>上场队员</th><th>赛季总积分</th><th>场均积分</th><th>胜率</th></tr></thead><tbody>{''.join(team_points_rows) or '<tr><td colspan="7" class="text-secondary">当前赛季还没有战队积分数据。</td></tr>'}</tbody></table></div></section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h2 class="section-title mb-2">专题选手积分排行榜</h2><p class="section-copy mb-0">该榜单会把同系列赛下不同地区、同一赛季的比赛一起统计，形成该系列赛赛季口径的选手积分榜。</p></div></div><div class="table-responsive"><table class="table align-middle"><thead><tr><th>排名</th><th>选手</th><th>战队</th><th>出场</th><th>战绩</th><th>赛季总积分</th><th>场均得分</th><th>胜率</th></tr></thead><tbody>{''.join(leaderboard_rows) or '<tr><td colspan="8" class="text-secondary">当前赛季还没有选手积分数据。</td></tr>'}</tbody></table></div></section>
    <section class="panel shadow-sm p-3 p-lg-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3"><div><h2 class="section-title mb-2">系列赛全部场次</h2><p class="section-copy mb-0">这里展示当前专题页下最近的场次，方便跨地区追踪同系列赛进展。</p></div></div><div class="table-responsive"><table class="table align-middle"><thead><tr><th>编号</th><th>地区</th><th>赛事页</th><th>日期</th><th>阶段</th><th>轮次</th><th>参赛战队</th><th>操作</th></tr></thead><tbody>{''.join(match_rows_html) or '<tr><td colspan="8" class="text-secondary">当前赛季还没有比赛记录。</td></tr>'}</tbody></table></div></section>
    """
    return layout(f"{series_rows[0]['series_name']} 专题页", body, ctx)


def get_match_day_page(ctx: RequestContext, played_on: str) -> str:
    if not is_valid_match_day(played_on):
        return layout("未找到比赛日", '<div class="alert alert-danger">比赛日期格式不正确。</div>', ctx)

    data = load_validated_data()
    catalog = load_series_catalog(data)
    player_lookup = {player["player_id"]: player for player in data["players"]}
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
        match_cards = []
        for match in sorted(
            matches,
            key=lambda item: ((item.get("season") or "").strip(), item["round"], item["game_no"], item["match_id"]),
        ):
            season_name = (match.get("season") or "").strip()
            detail_path = build_match_day_path(played_on)
            match_detail_path = f"/matches/{match['match_id']}?next={quote(detail_path)}"
            team_links = "、".join(
                f'<a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{legacy.escape(build_scoped_path("/teams/" + entry["team_id"], competition_name, season_name, region_name, series_slug))}">{legacy.escape(team_lookup[entry["team_id"]]["name"])}</a>'
                for entry in sorted(
                    {item["team_id"]: item for item in match["players"]}.values(),
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
            match_cards.append(
                f"""
                <div class="col-12">
                  <div class="team-link-card shadow-sm p-4 h-100">
                    <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-start gap-3 mb-3">
                      <div>
                        <div class="card-kicker mb-2">个人积分日报</div>
                        <h3 class="h5 mb-2">{legacy.escape(match['match_id'])}</h3>
                        <div class="small-muted">赛季 {legacy.escape(season_name)} · {legacy.escape(STAGE_OPTIONS.get(match['stage'], match['stage']))} · 第 {match['round']} 轮 / 第 {match['game_no']} 局</div>
                        <div class="small-muted mt-1">参赛战队 {team_links} · {legacy.escape(match['table_label'])} · {match['duration_minutes']} 分钟</div>
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
                          {''.join(player_rows)}
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
                  <p class="section-copy mb-0">当天该系列赛共有 {len(matches)} 场比赛，涉及 {team_count} 支战队、{player_count} 名队员。日报按单场个人积分展示，战队积分将累计进赛季排行榜。</p>
                </div>
                <a class="btn btn-outline-dark" href="{legacy.escape(build_scoped_path('/competitions', competition_name, (matches[0].get('season') or '').strip() or None, region_name, series_slug))}">进入该赛事页</a>
              </div>
              <div class="row g-3">{''.join(match_cards)}</div>
            </section>
            """
        )

    total_team_count = len({entry["team_id"] for match in day_matches for entry in match["players"]})
    total_player_count = len({entry["player_id"] for match in day_matches for entry in match["players"]})
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">比赛日总览</div>
          <h1 class="hero-title mb-3">{legacy.escape(played_on)} 比赛日</h1>
          <p class="hero-copy mb-0">这里按系列赛拆分展示这一天的全部比赛。你可以先看当天总览，再点进单场详情页继续查看每局完整数据。</p>
          <div class="d-flex flex-wrap gap-2 mt-4">
            <a class="btn btn-outline-dark" href="{legacy.escape(next_path)}">返回上一页</a>
          </div>
          <div class="hero-kpis">
            <div class="hero-pill"><span>系列赛数量</span><strong>{len(grouped_matches)}</strong><small>当天涉及系列赛</small></div>
            <div class="hero-pill"><span>比赛场次</span><strong>{len(day_matches)}</strong><small>当天全部比赛</small></div>
            <div class="hero-pill"><span>参赛战队</span><strong>{total_team_count}</strong><small>当天全部战队</small></div>
            <div class="hero-pill"><span>参赛队员</span><strong>{total_player_count}</strong><small>当天全部上场</small></div>
          </div>
        </div>
        <div class="hero-stage-card">
          <div class="official-mark">Official Match Day</div>
          <div class="hero-stage-label">Daily Overview</div>
          <div class="hero-stage-title">{legacy.escape(played_on)}</div>
          <div class="hero-stage-note">当天所有比赛会按系列赛分块展示，每场比赛都保留详情入口，方便回看当日完整赛程。</div>
          <div class="hero-stage-grid">
            <div class="hero-stage-metric"><span>系列赛</span><strong>{len(grouped_matches)}</strong><small>当天开赛系列赛</small></div>
            <div class="hero-stage-metric"><span>场次</span><strong>{len(day_matches)}</strong><small>当天完整对局</small></div>
            <div class="hero-stage-metric"><span>战队</span><strong>{total_team_count}</strong><small>当天参赛战队</small></div>
            <div class="hero-stage-metric"><span>队员</span><strong>{total_player_count}</strong><small>当天上场人数</small></div>
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
            layout("没有权限", '<div class="alert alert-danger">只有具备战队管理权限的账号、战队队长或管理员可以为战队报名赛季。</div>', ctx),
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
            if str(match.get("played_on") or "").strip()
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
