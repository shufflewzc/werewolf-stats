from __future__ import annotations

import json

import web_app as legacy

Any = legacy.Any
DEFAULT_PLAYER_PHOTO = legacy.DEFAULT_PLAYER_PHOTO
DEFAULT_REGION_NAME = legacy.DEFAULT_REGION_NAME
account_role_label = legacy.account_role_label
build_filtered_data = legacy.build_filtered_data
china_now_label = legacy.china_now_label
resolve_catalog_scope = legacy.resolve_catalog_scope
DEFAULT_AI_DAILY_BRIEF_MODEL = legacy.DEFAULT_AI_DAILY_BRIEF_MODEL
RequestContext = legacy.RequestContext
build_competition_switcher = legacy.build_competition_switcher
build_match_day_path = legacy.build_match_day_path
build_player_details = legacy.build_player_details
build_player_dimension_panel = legacy.build_player_dimension_panel
build_player_photo_html = legacy.build_player_photo_html
build_player_rows = legacy.build_player_rows
build_scoped_path = legacy.build_scoped_path
build_season_switcher = legacy.build_season_switcher
build_team_rows = legacy.build_team_rows
can_manage_player = legacy.can_manage_player
can_manage_player_bindings = legacy.can_manage_player_bindings
escape = legacy.escape
format_dimension_metric_value = legacy.format_dimension_metric_value
format_pct = legacy.format_pct
form_value = legacy.form_value
get_player_dimension_history = legacy.get_player_dimension_history
get_match_competition_name = legacy.get_match_competition_name
get_selected_competition = legacy.get_selected_competition
get_selected_season = legacy.get_selected_season
get_user_by_player_id = legacy.get_user_by_player_id
is_admin_user = legacy.is_admin_user
layout = legacy.layout
list_seasons = legacy.list_seasons
load_ai_daily_brief_settings = legacy.load_ai_daily_brief_settings
load_ai_player_season_summary = legacy.load_ai_player_season_summary
load_users = legacy.load_users
load_validated_data = legacy.load_validated_data
quote = legacy.quote
render_ai_daily_brief_html = legacy.render_ai_daily_brief_html
safe_rate = legacy.safe_rate
start_response_json = legacy.start_response_json
summarize_dimension_rows = legacy.summarize_dimension_rows
urlencode = legacy.urlencode


def _build_player_legacy_href(
    player_id: str,
    selected_competition: str | None,
    selected_season: str | None,
) -> str:
    return build_scoped_path(
        f"/players/{player_id}/legacy",
        selected_competition,
        selected_season if selected_competition else None,
    )


def _build_player_page_payload(ctx: RequestContext, player_id: str) -> dict[str, Any]:
    data = load_validated_data()
    users = load_users()
    player_matches = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
            reverse=True,
        )
        if any(entry["player_id"] == player_id for entry in match["players"])
    ]
    player_competition_names: list[str] = []
    for match in player_matches:
        competition_name = get_match_competition_name(match)
        if competition_name not in player_competition_names:
            player_competition_names.append(competition_name)

    selected_competition = get_selected_competition(ctx, player_competition_names)
    season_names = (
        list_seasons(
            {
                "matches": [
                    match
                    for match in player_matches
                    if get_match_competition_name(match) == selected_competition
                ]
            },
            selected_competition,
        )
        if selected_competition
        else []
    )
    selected_season = get_selected_season(ctx, season_names)
    competition_switcher = build_competition_switcher(
        f"/players/{player_id}",
        player_competition_names,
        selected_competition,
        tone="light",
    )
    season_switcher = build_season_switcher(
        f"/players/{player_id}",
        selected_competition,
        season_names,
        selected_season,
        tone="light",
    )
    player_rows = build_player_rows(data, selected_competition, selected_season)
    row_lookup = {row["player_id"]: row for row in player_rows}
    player_details = build_player_details(
        data,
        player_rows,
        selected_competition,
        selected_season,
    )
    detail = player_details.get(player_id)
    if not detail:
        return {
            "not_found": True,
            "title": "未找到队员",
            "body_html": '<div class="alert alert-danger">没有找到对应的队员。</div>',
            "legacy_href": _build_player_legacy_href(player_id, selected_competition, selected_season),
        }

    players = {player["player_id"]: player for player in data["players"]}
    player = players[player_id]
    owner_user = get_user_by_player_id(users, player_id)
    player_row = row_lookup[player_id]
    team_id = player_row["team_id"]
    aliases = "、".join(detail["aliases"]) if detail["aliases"] else "无"
    photo_html = build_player_photo_html(detail["photo"], detail["display_name"])
    manage_buttons: list[str] = []
    if ctx.current_user and ctx.current_user.get("player_id") == player_id:
        manage_buttons.append('<a class="btn btn-light text-dark shadow-sm" href="/profile">编辑我的资料</a>')
    elif can_manage_player(ctx, player_id):
        manage_buttons.append(
            f'<a class="btn btn-light text-dark shadow-sm" '
            f'href="/players/{escape(player_id)}/edit?{urlencode({"next": build_scoped_path("/players/" + player_id, selected_competition, selected_season)})}">编辑队员资料</a>'
        )
    if ctx.current_user and can_manage_player_bindings(data, ctx.current_user, owner_user, player):
        binding_query = {"player_id": player_id}
        if owner_user:
            binding_query["username"] = owner_user["username"]
        manage_buttons.append(
            f'<a class="btn btn-outline-light text-dark shadow-sm" href="/bindings?{urlencode(binding_query)}">管理赛事绑定</a>'
        )
    manage_button_row = (
        f'<div class="d-flex flex-wrap gap-2 mt-3">{"".join(manage_buttons)}</div>' if manage_buttons else ""
    )
    season_chip = f'<span class="chip">{escape(selected_season)}</span>' if selected_season else ""
    player_team_path = build_scoped_path("/teams/" + team_id, selected_competition, selected_season)
    legacy_href = _build_player_legacy_href(player_id, selected_competition, selected_season)
    overall_win_width = max(0.0, min(100.0, float(player_row.get("win_rate", 0.0)) * 100.0))
    villagers_win_width = max(0.0, min(100.0, float(player_row.get("villagers_win_rate", 0.0)) * 100.0))
    werewolves_win_width = max(0.0, min(100.0, float(player_row.get("werewolves_win_rate", 0.0)) * 100.0))
    role_total = sum(item["games"] for item in detail["roles"])

    role_cards_html = "".join(
        f"""
        <article class="player-role-card">
          <div class="player-role-top">
            <div>
              <div class="player-role-name">{escape(item["role"])}</div>
              <div class="player-role-meta">当前口径下共登场 {item["games"]} 局</div>
            </div>
            <div class="player-role-count">{item["games"]} 局</div>
          </div>
          <div class="player-role-track">
            <div class="player-role-fill" style="width: {safe_rate(item['games'], role_total) * 100:.1f}%"></div>
          </div>
          <div class="player-role-share">角色占比 {format_pct(safe_rate(item["games"], role_total))}</div>
        </article>
        """
        for item in detail["roles"][:6]
    ) or """
        <article class="player-role-card">
          <div class="player-role-name">暂无角色记录</div>
          <div class="player-role-meta mt-2">当前筛选范围内还没有可展示的角色分布数据。</div>
        </article>
    """

    season_cards_html = "".join(
        f"""
        <article class="player-season-card">
          <div class="player-season-top">
            <div>
              <div class="player-season-name">{escape(item["season_name"])}</div>
              <div class="player-season-meta">{escape(item["competition_name"])}</div>
            </div>
            <div class="player-season-points">{escape(item["points_total"])} 分</div>
          </div>
          <div class="player-season-stats">
            <span class="player-stat-pill">出场 {item["games_played"]}</span>
            <span class="player-stat-pill">战绩 {escape(item["record"])}</span>
            <span class="player-stat-pill">总胜率 {escape(item["overall_win_rate"])}</span>
            <span class="player-stat-pill">场均 {escape(item["average_points"])}</span>
          </div>
        </article>
        """
        for item in detail["season_stats"][:4]
    ) or """
        <article class="player-season-card">
          <div class="player-season-name">暂无赛季切片</div>
          <div class="player-season-meta mt-2">当前筛选范围内还没有形成可展示的小赛季统计。</div>
        </article>
    """

    recent_match_cards: list[str] = []
    for item in detail["history"][:4]:
        match_detail_path = (
            f"/matches/{item['match_id']}?next="
            f"{quote(build_scoped_path('/players/' + player_id, selected_competition, selected_season))}"
        )
        day_path = build_match_day_path(
            item["played_on"],
            build_scoped_path("/players/" + player_id, selected_competition, selected_season),
        )
        result_class = ""
        if item["result_label"] == "胜利":
            result_class = " is-win"
        elif item["result_label"] == "失利":
            result_class = " is-loss"
        award_pills = "".join(
            f'<span class="player-stat-pill">{escape(label)}</span>'
            for label in item.get("award_labels", [])
        ) or '<span class="player-stat-pill">无特殊奖励</span>'
        recent_match_cards.append(
            f"""
            <article class="player-match-card">
              <div class="player-match-top">
                <div>
                  <div class="player-match-name">{escape(item["competition_name"])}</div>
                  <div class="player-match-meta">{escape(item["season"])} · {escape(item["stage_label"])} · 第 {item["round"]} 轮 · {escape(item["played_on"])}</div>
                </div>
                <span class="player-match-result{result_class}">{escape(item["result_label"])}</span>
              </div>
              <div class="player-match-tags">
                <span class="player-stat-pill">得分 {item["points_earned"]:.2f}</span>
                {award_pills}
              </div>
              <div class="player-match-actions">
                <a class="btn btn-sm btn-outline-dark" href="{escape(match_detail_path)}">比赛详情</a>
                <a class="btn btn-sm btn-light border" href="{escape(day_path)}">当日赛程</a>
              </div>
            </article>
            """
        )
    recent_match_cards_html = "".join(recent_match_cards) or """
        <article class="player-match-card">
          <div class="player-match-name">暂无近期比赛</div>
          <div class="player-match-meta mt-2">当前筛选范围内还没有可展示的对局记录。</div>
        </article>
    """

    history_rows = []
    for item in detail["history"]:
        match_detail_path = (
            f"/matches/{item['match_id']}?next="
            f"{quote(build_scoped_path('/players/' + player_id, selected_competition, selected_season))}"
        )
        day_path = build_match_day_path(
            item["played_on"],
            build_scoped_path("/players/" + player_id, selected_competition, selected_season),
        )
        history_rows.append(
            f"""
            <tr>
              <td>{escape(item['competition_name'])}</td>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(day_path)}">{escape(item['played_on'])}</a></td>
              <td>{escape(item['season'])}</td>
              <td>{escape(item['stage_label'])}</td>
              <td>第 {item['round']} 轮</td>
              <td>{escape(item['role'])}</td>
              <td>{escape(item['camp_label'])}</td>
              <td>{escape(item['result_label'])}</td>
              <td>{escape(item['stance_result_label'])}</td>
              <td>{item['points_earned']:.2f}</td>
              <td>{escape(item['notes'] or '无')}</td>
              <td><a class="btn btn-sm btn-outline-dark" href="{escape(match_detail_path)}">查看比赛</a></td>
            </tr>
            """
        )

    season_rows = []
    for item in detail["season_stats"]:
        season_rows.append(
            f"""
            <tr>
              <td>{escape(item['competition_name'])}</td>
              <td>{escape(item['season_name'])}</td>
              <td>{item['games_played']}</td>
              <td>{escape(item['record'])}</td>
              <td>{escape(item['overall_win_rate'])}</td>
              <td>{escape(item['villagers_win_rate'])}</td>
              <td>{escape(item['werewolves_win_rate'])}</td>
              <td>{escape(item['points_total'])}</td>
              <td>{escape(item['average_points'])}</td>
            </tr>
            """
        )
    season_detail_section = (
        f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">完整赛季明细</h2>
          <p class="section-copy mb-0">这里保留完整表格，方便继续核对每个小赛季的胜率和积分口径。</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>赛事</th>
              <th>赛季</th>
              <th>出场</th>
              <th>战绩</th>
              <th>总胜率</th>
              <th>好人胜率</th>
              <th>狼人胜率</th>
              <th>总积分</th>
              <th>场均得分</th>
            </tr>
          </thead>
          <tbody>
            {''.join(season_rows) or '<tr><td colspan="9" class="text-secondary">当前统计口径下暂无赛季胜率数据。</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
    """
        if len(detail["season_stats"]) > 1
        else ""
    )
    player_dimension_panel = build_player_dimension_panel(
        ctx,
        data,
        player_id,
        selected_competition,
        selected_season,
    )
    ai_player_season_summary = (
        load_ai_player_season_summary(player_id, selected_competition, selected_season)
        if selected_competition and selected_season
        else None
    )
    ai_settings = load_ai_daily_brief_settings()
    ai_configured = bool(ai_settings.get("base_url") and ai_settings.get("api_key"))
    ai_player_summary_actions = ""
    ai_player_summary_admin_editor = ""
    if selected_competition and selected_season:
        if ai_configured and (not ai_player_season_summary or is_admin_user(ctx.current_user)):
            ai_player_summary_actions = f"""
            <form method="post" action="/players/{escape(player_id)}" class="m-0">
              <input type="hidden" name="action" value="generate_ai_player_season_summary">
              <input type="hidden" name="competition_name" value="{escape(selected_competition)}">
              <input type="hidden" name="season_name" value="{escape(selected_season)}">
              <button type="submit" class="btn btn-dark">{'重生成 AI 选手赛季总结' if ai_player_season_summary else '生成 AI 选手赛季总结'}</button>
            </form>
            """
        elif not ai_configured and is_admin_user(ctx.current_user):
            ai_player_summary_actions = '<a class="btn btn-outline-dark" href="/accounts">前往账号管理配置 AI 接口</a>'
        if ai_player_season_summary and is_admin_user(ctx.current_user):
            ai_player_summary_admin_editor = f"""
            <div class="form-panel p-3 p-lg-4 mt-4">
              <h3 class="h5 mb-2">管理员编辑总结</h3>
              <p class="section-copy mb-3">可以直接修改当前总结正文。保存后会立即覆盖展示内容。</p>
              <form method="post" action="/players/{escape(player_id)}">
                <input type="hidden" name="action" value="save_ai_player_season_summary">
                <input type="hidden" name="competition_name" value="{escape(selected_competition)}">
                <input type="hidden" name="season_name" value="{escape(selected_season)}">
                <div class="mb-3">
                  <textarea class="form-control" name="summary_content" rows="12">{escape(ai_player_season_summary.get('content') or '')}</textarea>
                </div>
                <div class="d-flex flex-wrap gap-2">
                  <button type="submit" class="btn btn-outline-dark">保存人工编辑</button>
                </div>
              </form>
            </div>
            """
    ai_player_summary_panel = ""
    if selected_season:
        ai_player_summary_panel = (
            f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
                <div>
                  <h2 class="section-title mb-2">AI 选手赛季总结</h2>
                  <p class="section-copy mb-0">基于当前选手在这个赛事赛季下的真实战绩、角色分布和比赛记录生成总结。首次生成对所有访客开放；生成后仅管理员可重生成或编辑。</p>
                </div>
                <div class="d-flex flex-wrap gap-2">{ai_player_summary_actions}</div>
              </div>
              <div class="small text-secondary mb-3">生成时间 {escape(ai_player_season_summary.get('generated_at') or '未生成')} · 模型 {escape(ai_player_season_summary.get('model') or ai_settings.get('model') or DEFAULT_AI_DAILY_BRIEF_MODEL)}</div>
              <div class="editorial-copy mb-0">{render_ai_daily_brief_html(ai_player_season_summary.get('content') or '')}</div>
              {ai_player_summary_admin_editor}
            </section>
            """
            if ai_player_season_summary
            else f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3">
                <div>
                  <h2 class="section-title mb-2">AI 选手赛季总结</h2>
                  <p class="section-copy mb-0">{escape('当前赛季还没有生成 AI 总结，首次生成对所有访客开放。' if ai_configured else '当前还没有配置 AI 接口。配置后即可在这里生成选手赛季总结。')}</p>
                </div>
                <div class="d-flex flex-wrap gap-2">{ai_player_summary_actions}</div>
              </div>
            </section>
            """
        )

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="row g-4 align-items-center">
        <div class="col-12 col-lg-4 col-xl-3">
          {photo_html}
        </div>
        <div class="col-12 col-lg-8 col-xl-9">
          <div class="eyebrow mb-3">队员个人页面</div>
          <h1 class="display-6 fw-semibold mb-3">{escape(detail['display_name'])}</h1>
          <p class="mb-2 opacity-75">{escape(detail['team_name'])} · 当前排名第 {detail['rank']} 名</p>
          <div class="d-flex flex-wrap gap-2 mt-3">{competition_switcher}</div>
          {f'<div class="d-flex flex-wrap gap-2 mt-3">{season_switcher}</div>' if season_switcher else ''}
          {manage_button_row}
          <div class="d-flex flex-wrap gap-2 mt-3">
            <a class="btn btn-outline-light text-dark shadow-sm" href="{escape(legacy_href)}">旧版队员页</a>
          </div>
          <div class="d-flex flex-wrap gap-3 mt-5 pt-1">
            {season_chip}
            <span class="chip">战绩 {escape(detail['record'])}</span>
            <span class="chip">总胜率 {escape(detail['overall_win_rate'])}</span>
            <span class="chip">好人胜率 {escape(detail['villagers_win_rate'])}</span>
            <span class="chip">狼人胜率 {escape(detail['werewolves_win_rate'])}</span>
            <span class="chip">总积分 {escape(detail['points_total'])}</span>
          </div>
        </div>
      </div>
    </section>
    {player_dimension_panel}
    {ai_player_summary_panel}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">选手数据档案</h2>
          <p class="section-copy mb-0">先用一屏把这位选手的状态、特征和近期走势讲清楚，下面再接完整明细表。</p>
        </div>
      </div>
      <div class="player-showcase-grid">
        <article class="player-showcase-card">
          <div class="player-masthead">
            <div class="player-masthead-copy">
              <div class="eyebrow">Season Player</div>
              <div class="player-headline">{escape(detail['display_name'])}</div>
              <div class="player-subtitle">{escape(detail['team_name'])} · 当前排名第 {detail['rank']} 名 · 战绩 {escape(detail['record'])}</div>
              <div class="player-masthead-meta">
                <span class="player-badge">总出场 {detail['games_played']}</span>
                <span class="player-badge">总积分 {escape(detail['points_total'])}</span>
                <span class="player-badge">场均 {escape(detail['average_points'])}</span>
              </div>
            </div>
          </div>
          <div class="player-kpi-grid">
            <div class="player-kpi-card">
              <div class="player-kpi-label">Current Team</div>
              <div class="player-kpi-value"><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(player_team_path)}">{escape(detail['team_name'])}</a></div>
              <div class="player-kpi-copy">按当前赛事筛选口径归属战队</div>
            </div>
            <div class="player-kpi-card">
              <div class="player-kpi-label">Total Games</div>
              <div class="player-kpi-value">{detail['games_played']}</div>
              <div class="player-kpi-copy">当前范围内已录入对局数</div>
            </div>
            <div class="player-kpi-card">
              <div class="player-kpi-label">Win Rate</div>
              <div class="player-kpi-value">{escape(detail['overall_win_rate'])}</div>
              <div class="player-kpi-copy">综合胜率表现</div>
            </div>
            <div class="player-kpi-card">
              <div class="player-kpi-label">Avg Points</div>
              <div class="player-kpi-value">{escape(detail['average_points'])}</div>
              <div class="player-kpi-copy">单局积分产出效率</div>
            </div>
            <div class="player-kpi-card">
              <div class="player-kpi-label">Points Total</div>
              <div class="player-kpi-value">{escape(detail['points_total'])}</div>
              <div class="player-kpi-copy">累计积分沉淀</div>
            </div>
            <div class="player-kpi-card">
              <div class="player-kpi-label">Stance Calls</div>
              <div class="player-kpi-value">{detail['correct_stances']} / {detail['stance_calls']}</div>
              <div class="player-kpi-copy">站边判断命中次数</div>
            </div>
          </div>
        </article>
        <aside class="player-insight-card">
          <div>
            <h3 class="section-title mb-2">核心能力观察</h3>
            <p class="section-copy mb-0">把几条最关键的指标抽出来，方便一眼看出这名选手更偏稳定型、进攻型还是阵营特化型。</p>
          </div>
          <div class="player-skill-row">
            <div class="player-skill-head">
              <strong>综合胜率</strong>
              <span>{escape(detail['overall_win_rate'])}</span>
            </div>
            <div class="player-skill-track"><div class="player-skill-fill" style="width: {overall_win_width:.1f}%"></div></div>
          </div>
          <div class="player-skill-row">
            <div class="player-skill-head">
              <strong>好人胜率</strong>
              <span>{escape(detail['villagers_win_rate'])}</span>
            </div>
            <div class="player-skill-track"><div class="player-skill-fill" style="width: {villagers_win_width:.1f}%"></div></div>
          </div>
          <div class="player-skill-row">
            <div class="player-skill-head">
              <strong>狼人胜率</strong>
              <span>{escape(detail['werewolves_win_rate'])}</span>
            </div>
            <div class="player-skill-track"><div class="player-skill-fill" style="width: {werewolves_win_width:.1f}%"></div></div>
          </div>
          <div class="player-note-grid">
            <div class="player-note-item">
              <div class="player-note-label">Aliases</div>
              <div class="player-note-value">{escape(aliases)}</div>
            </div>
            <div class="player-note-item">
              <div class="player-note-label">Joined</div>
              <div class="player-note-value">{escape(detail['joined_on'])}</div>
            </div>
            <div class="player-note-item">
              <div class="player-note-label">Profile Status</div>
              <div class="player-note-value">{escape('已配置头像资料' if detail['photo'] else '使用默认头像')}</div>
            </div>
            <div class="player-note-item">
              <div class="player-note-label">Notes</div>
              <div class="player-note-value">{escape(detail['notes'] or '暂无补充备注')}</div>
            </div>
          </div>
        </aside>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-4">
        <div class="col-12 col-xl-6">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">角色画像</h2>
              <p class="section-copy mb-0">不是只显示几个标签，而是直接看出这个人最常站在哪些位置。</p>
            </div>
          </div>
          <div class="player-roles-grid">{role_cards_html}</div>
        </div>
        <div class="col-12 col-xl-6">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">最近四场</h2>
              <p class="section-copy mb-0">用最近对局做一个趋势窗口，刷新时不用先翻整张长表。</p>
            </div>
          </div>
          <div class="player-match-grid">{recent_match_cards_html}</div>
        </div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h2 class="section-title mb-2">赛季切片</h2>
      <p class="section-copy mb-3">当前球员档案按赛季独立建档，所以这里只看这个赛季身份下的阶段表现，不做跨赛事合并。</p>
      <div class="player-season-grid">{season_cards_html}</div>
    </section>
    {season_detail_section}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h2 class="section-title mb-2">角色标签摘要</h2>
      <p class="section-copy mb-3">如果你只想快速扫一眼角色池，也可以直接看这组简洁标签。</p>
      <div class="d-flex flex-wrap gap-2">
        {"".join(f'<span class="chip">{escape(item["role"])} {item["games"]} 局</span>' for item in detail["roles"]) or '<span class="chip">暂无角色记录</span>'}
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">全部比赛记录</h2>
          <p class="section-copy mb-0">完整对局明细继续保留在这里，方便你往下查到具体每一盘。</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>赛事</th>
              <th>日期</th>
              <th>赛季</th>
              <th>阶段</th>
              <th>轮次</th>
              <th>角色</th>
              <th>阵营</th>
              <th>结果</th>
              <th>站边</th>
              <th>得分</th>
              <th>备注</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {''.join(history_rows)}
          </tbody>
        </table>
      </div>
    </section>
    """
    return {
        "title": f"{detail['display_name']} 页面",
        "body_html": body,
        "legacy_href": legacy_href,
    }


def build_players_frontend_page(ctx: RequestContext) -> str:
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
            "apiEndpoint": "/api/players",
            "alert": form_value(ctx.query, "alert").strip(),
        },
        ensure_ascii=False,
    )
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#122238">
    <title>选手</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;800;900&family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/competitions-app.css">
  </head>
  <body class="competitions-app-shell players-app-shell">
    <div class="shell-backdrop"></div>
    <header class="shell-header">
      <div class="shell-brand">
        <a class="shell-brand-link" href="/dashboard" aria-label="返回赛事首页">
          <span class="shell-brand-mark" aria-hidden="true"></span>
          <span>WOLF</span>
        </a>
        <span class="shell-brand-copy">赛季选手 · API Driven</span>
      </div>
      <nav class="shell-nav" aria-label="主导航">
        <a class="shell-nav-link" href="/dashboard">仪表盘</a>
        <a class="shell-nav-link" href="/competitions">比赛中心</a>
        <a class="shell-nav-link" href="/teams">战队</a>
        <a class="shell-nav-link is-active" href="/players">选手</a>
        <a class="shell-nav-link" href="/guilds">门派</a>
        <a class="shell-nav-link" href="/schedule">赛程日历</a>
      </nav>
      {account_html}
    </header>
    <main id="players-app" class="competitions-app-root players-app-root" aria-live="polite">
      <section class="competitions-loading-shell">
        <div class="competitions-loading-kicker">Loading Players</div>
        <h1>正在加载赛季选手数据</h1>
        <p>前端会按已选择的赛事赛季拉取选手数据并渲染页面。</p>
      </section>
    </main>
    <script>window.__WEREWOLF_PLAYERS_BOOTSTRAP__ = {bootstrap};</script>
    <script src="/assets/players-app.js" defer></script>
  </body>
</html>
"""


def build_players_api_payload(ctx: RequestContext) -> dict[str, Any]:
    data = load_validated_data()
    scope = resolve_catalog_scope(ctx, data)
    selected_competition = scope["selected_competition"]
    selected_entry = scope["selected_entry"]
    selected_region = scope["selected_region"]
    selected_series_slug = scope["selected_series_slug"]
    region_rows = scope["region_rows"]
    filtered_rows = scope["filtered_rows"]
    series_rows = scope["series_rows"]
    season_names = list_seasons(data, selected_competition) if selected_competition else []
    selected_season = get_selected_season(ctx, season_names)
    scoped_competition_rows = filtered_rows or region_rows or scope["competition_rows"]
    region_options = [
        {
            "label": region_name,
            "href": build_scoped_path("/players", None, None, region_name, selected_series_slug),
            "active": selected_region == region_name,
        }
        for region_name in scope["region_names"]
    ]
    series_options = [
        {
            "label": "全部系列赛",
            "href": build_scoped_path("/players", None, None, selected_region, None),
            "active": selected_series_slug is None,
        }
    ] + [
        {
            "label": row["series_name"],
            "href": build_scoped_path("/players", None, None, selected_region, row["series_slug"]),
            "active": selected_series_slug == row["series_slug"],
        }
        for row in series_rows
    ]
    competition_options = [
        {
            "label": row["competition_name"],
            "href": build_scoped_path("/players", row["competition_name"], None, selected_region, selected_series_slug),
            "active": selected_competition == row["competition_name"],
        }
        for row in scoped_competition_rows
    ]
    season_options = [
        {
            "label": season_name,
            "href": build_scoped_path("/players", selected_competition, season_name, selected_region, selected_series_slug),
            "selected": selected_season == season_name,
        }
        for season_name in season_names
    ]
    if not selected_competition or not selected_season:
        return {
            "generated_at": china_now_label(),
            "requires_scope": True,
            "scope": {
                "label": "请先选择赛事赛季",
                "description": "选手不是全站独立列表，必须先选择具体赛事和赛季，再查看该赛季内的选手数据。",
                "filters": {
                    "regions": region_options,
                    "series": series_options,
                    "competitions": competition_options,
                    "seasons": season_options,
                },
            },
            "metrics": [],
            "players": [],
        }
    scoped_competition_names = {row["competition_name"] for row in scoped_competition_rows}
    stats_data = (
        build_filtered_data(data, scoped_competition_names)
        if not selected_competition and scoped_competition_names
        else data
    )
    player_rows = build_player_rows(stats_data, selected_competition, selected_season)
    visible_rows = [row for row in player_rows if row.get("games_played", 0) > 0]
    displayed_rows = visible_rows or player_rows
    displayed_rows.sort(
        key=lambda row: (
            int(row.get("rank") or 9999),
            -float(row.get("points_earned_total") or 0.0),
            row.get("display_name") or "",
        )
    )
    scope_label = " / ".join(
        item
        for item in [
            selected_region or DEFAULT_REGION_NAME,
            selected_entry["series_name"] if selected_entry else None,
            selected_competition,
            selected_season,
        ]
        if item
    ) or f"{DEFAULT_REGION_NAME}赛区汇总"
    players = [
        {
            "rank": int(row.get("rank") or index + 1),
            "player_id": row["player_id"],
            "display_name": row["display_name"],
            "team_name": row.get("team_name") or row.get("current_team_name") or "未绑定战队",
            "photo": row.get("photo") or DEFAULT_PLAYER_PHOTO,
            "games_played": int(row.get("games_played") or 0),
            "wins": int(row.get("wins") or 0),
            "losses": int(row.get("losses") or 0),
            "record": row.get("record") or f"{int(row.get('wins') or 0)}-{int(row.get('losses') or 0)}",
            "points_total": f"{float(row.get('points_earned_total') or 0.0):.2f}",
            "average_points": f"{float(row.get('average_points') or 0.0):.2f}",
            "win_rate": format_pct(float(row.get("win_rate") or 0.0)),
            "stance_rate": format_pct(float(row.get("stance_rate") or 0.0)),
            "href": build_scoped_path(
                "/players/" + row["player_id"],
                selected_competition,
                selected_season,
                selected_region,
                selected_series_slug,
            ),
        }
        for index, row in enumerate(displayed_rows)
    ]
    top_player = players[0] if players else None
    return {
        "generated_at": china_now_label(),
        "scope": {
            "label": scope_label,
            "description": f"当前正在查看 {scope_label} 这个赛事赛季内的选手积分、胜率和出场数据。",
            "filters": {
                "regions": region_options,
                "series": series_options,
                "competitions": competition_options,
                "seasons": season_options,
            },
        },
        "metrics": [
            {"label": "收录选手", "value": str(len(players)), "copy": "当前范围内可展示的选手数量。"},
            {"label": "有效选手", "value": str(len([player for player in players if player["games_played"] > 0])), "copy": "至少有一局有效比赛记录的选手。"},
            {"label": "总出场", "value": str(sum(player["games_played"] for player in players)), "copy": "所有选手的出场局数合计。"},
            {"label": "榜首选手", "value": top_player["display_name"] if top_player else "待录入", "copy": "按当前积分排行口径计算。"},
        ],
        "players": players,
    }


def handle_players_api(ctx: RequestContext, start_response):
    if ctx.method != "GET":
        return start_response_json(
            start_response,
            "405 Method Not Allowed",
            {"error": "players api only supports GET"},
            headers=[("Allow", "GET")],
        )
    return start_response_json(start_response, "200 OK", build_players_api_payload(ctx))


def build_player_frontend_page(ctx: RequestContext, player_id: str) -> str:
    data = load_validated_data()
    player = next((item for item in data["players"] if item["player_id"] == player_id), None)
    if not player:
        return layout("未找到队员", '<div class="alert alert-danger">没有找到对应的队员。</div>', ctx)

    requested_competition = form_value(ctx.query, "competition").strip() or None
    requested_season = form_value(ctx.query, "season").strip() or None
    bootstrap = json.dumps(
        {
            "apiEndpoint": f"/api/players/{player_id}",
            "alert": form_value(ctx.query, "alert").strip(),
            "legacyHref": _build_player_legacy_href(player_id, requested_competition, requested_season),
        },
        ensure_ascii=False,
    )

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#122238">
    <title>{escape(str(player.get('display_name') or player_id))} 页面</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;800;900&family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/competitions-app.css">
  </head>
  <body class="competitions-app-shell player-detail-app-shell">
    <div class="shell-backdrop"></div>
    <header class="shell-header">
      <div class="shell-brand">
        <a class="shell-brand-link" href="/dashboard" aria-label="返回赛事首页">
          <span class="shell-brand-mark" aria-hidden="true"></span>
          <span>WOLF</span>
        </a>
        <span class="shell-brand-copy">赛季选手 · API Driven</span>
      </div>
      <nav class="shell-nav" aria-label="主导航">
        <a class="shell-nav-link" href="/dashboard">仪表盘</a>
        <a class="shell-nav-link" href="/competitions">比赛中心</a>
        <a class="shell-nav-link" href="/teams">战队</a>
        <a class="shell-nav-link is-active" href="/players">选手</a>
        <a class="shell-nav-link" href="/guilds">门派</a>
        <a class="shell-nav-link" href="/schedule">赛程日历</a>
      </nav>
      {_build_player_account_html(ctx)}
    </header>
    <main id="player-app" class="competitions-layout player-detail-layout" aria-live="polite">
      <section class="competitions-panel competitions-loading-shell">
        <div class="competitions-section-kicker">Loading Player</div>
        <h1 class="competitions-title">正在加载赛季选手详情</h1>
        <p class="competitions-copy">新前端会按当前赛事赛季拉取选手数据、角色画像和最近比赛。</p>
      </section>
    </main>
    <script>window.__WEREWOLF_PLAYER_BOOTSTRAP__ = {bootstrap};</script>
    <script src="/assets/player-app.js" defer></script>
  </body>
</html>
"""


def _build_player_account_html(ctx: RequestContext) -> str:
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
          <a class="shell-button shell-button-primary" href="/register">注册</a>
        </div>
        """


def _player_asset_href(path: str | None) -> str:
    clean_path = str(path or "").strip() or DEFAULT_PLAYER_PHOTO
    if clean_path.startswith(("http://", "https://", "/")):
        return clean_path
    return f"/{clean_path}"


def _pct_width(value: str) -> float:
    try:
        return max(0.0, min(100.0, float(str(value).rstrip("%"))))
    except ValueError:
        return 0.0


def _serialize_player_detail_payload(ctx: RequestContext, player_id: str) -> dict[str, Any]:
    data = load_validated_data()
    users = load_users()
    player_matches = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
            reverse=True,
        )
        if any(entry["player_id"] == player_id for entry in match["players"])
    ]
    player_competition_names: list[str] = []
    for match in player_matches:
        competition_name = get_match_competition_name(match)
        if competition_name not in player_competition_names:
            player_competition_names.append(competition_name)
    selected_competition = get_selected_competition(ctx, player_competition_names)
    season_names = (
        list_seasons(
            {"matches": [match for match in player_matches if get_match_competition_name(match) == selected_competition]},
            selected_competition,
        )
        if selected_competition
        else []
    )
    selected_season = get_selected_season(ctx, season_names)
    legacy_href = _build_player_legacy_href(player_id, selected_competition, selected_season)
    if not selected_competition or not selected_season:
        return {
            "requires_scope": True,
            "title": "请先选择赛季",
            "message": "选手数据属于具体赛事赛季，请先从比赛中心选择赛季后再查看选手。",
            "actions": {
                "competitions_href": "/competitions",
                "legacy_href": legacy_href,
            },
        }
    player_rows = build_player_rows(data, selected_competition, selected_season)
    row_lookup = {row["player_id"]: row for row in player_rows}
    details = build_player_details(data, player_rows, selected_competition, selected_season)
    detail = details.get(player_id)
    player_lookup = {player["player_id"]: player for player in data["players"]}
    player = player_lookup.get(player_id)
    if not detail or not player:
        return {
            "not_found": True,
            "error": "没有找到对应的队员。",
            "title": "未找到队员",
            "alert": form_value(ctx.query, "alert").strip(),
            "legacy_href": legacy_href,
        }

    row = row_lookup.get(player_id, {})
    owner_user = get_user_by_player_id(users, player_id)
    team_id = str(row.get("team_id") or player.get("team_id") or "").strip()
    team_href = build_scoped_path(f"/teams/{team_id}", selected_competition, selected_season) if team_id else "/teams"
    manage_href = ""
    if ctx.current_user and ctx.current_user.get("player_id") == player_id:
        manage_href = "/profile"
    elif can_manage_player(ctx, player_id):
        manage_href = f"/players/{quote(player_id)}/edit?{urlencode({'next': build_scoped_path('/players/' + player_id, selected_competition, selected_season)})}"
    binding_href = ""
    if ctx.current_user and can_manage_player_bindings(data, ctx.current_user, owner_user, player):
        binding_query = {"player_id": player_id}
        if owner_user:
            binding_query["username"] = owner_user["username"]
        binding_href = f"/bindings?{urlencode(binding_query)}"

    role_total = sum(int(item.get("games") or 0) for item in detail["roles"])
    roles = [
        {
            "role": item["role"],
            "games": int(item["games"]),
            "share": format_pct(safe_rate(item["games"], role_total)),
            "width": round(safe_rate(item["games"], role_total) * 100, 1),
        }
        for item in detail["roles"]
    ]
    history = []
    for item in detail["history"]:
        history.append(
            {
                **item,
                "href": f"/matches/{quote(str(item['match_id']))}?{urlencode({'competition': item['competition_name'], 'season': item['season']})}",
            }
        )

    dimension = _serialize_player_dimension_payload(
        ctx,
        data,
        player_id,
        selected_competition,
        selected_season,
    )

    return {
        "title": f"{detail['display_name']} 页面",
        "alert": form_value(ctx.query, "alert").strip(),
        "generated_at": china_now_label(),
        "legacy_href": legacy_href,
        "scope": {
            "competition": selected_competition,
            "season": selected_season,
            "competition_options": player_competition_names,
            "season_options": season_names,
        },
        "player": {
            "player_id": player_id,
            "name": detail["display_name"],
            "photo": _player_asset_href(detail.get("photo")),
            "team_name": detail["team_name"],
            "team_href": team_href,
            "rank": detail["rank"],
            "aliases": detail["aliases"],
            "joined_on": detail["joined_on"],
            "notes": detail["notes"],
            "owner": owner_user.get("display_name") or owner_user.get("username") if owner_user else "未绑定账号",
        },
        "actions": {
            "players_href": build_scoped_path("/players", selected_competition, selected_season),
            "team_href": team_href,
            "legacy_href": legacy_href,
            "manage_href": manage_href,
            "binding_href": binding_href,
        },
        "metrics": [
            {"label": "排名", "value": f"#{detail['rank']}", "copy": "当前积分榜名次"},
            {"label": "战绩", "value": detail["record"], "copy": "当前口径胜负"},
            {"label": "总积分", "value": detail["points_total"], "copy": "当前赛季累计"},
            {"label": "场均积分", "value": detail["average_points"], "copy": "每局稳定产出"},
            {"label": "出赛局数", "value": str(detail["games_played"]), "copy": "有效比赛记录"},
            {"label": "站边率", "value": detail["stance_rate"], "copy": "已填写站边统计"},
        ],
        "insights": {
            "overall_win_rate": detail["overall_win_rate"],
            "overall_width": _pct_width(detail["overall_win_rate"]),
            "villagers_win_rate": detail["villagers_win_rate"],
            "villagers_width": _pct_width(detail["villagers_win_rate"]),
            "werewolves_win_rate": detail["werewolves_win_rate"],
            "werewolves_width": _pct_width(detail["werewolves_win_rate"]),
        },
        "roles": roles,
        "recent_matches": history[:6],
        "season_stats": detail["season_stats"],
        "dimension": dimension,
        "competition_stats": detail["competition_stats"],
        "history": history,
    }


def _serialize_player_dimension_payload(
    ctx: RequestContext,
    data: dict[str, Any],
    player_id: str,
    competition_name: str | None,
    season_name: str | None,
) -> dict[str, Any]:
    if not competition_name:
        return {"available": False, "reason": "请先选择赛事。"}
    all_rows = get_player_dimension_history(data, player_id, competition_name, None)
    if not all_rows:
        return {
            "available": False,
            "reason": "当前还没有导入对应选手的赛季维度补充数据。",
        }
    available_seasons = []
    for row in all_rows:
        item = str(row.get("season_name") or "").strip()
        if item and item not in available_seasons:
            available_seasons.append(item)
    requested_dimension_season = form_value(ctx.query, "dimension_season").strip()
    selected_dimension_season = (
        requested_dimension_season
        if requested_dimension_season in available_seasons
        else (season_name if season_name in available_seasons else (available_seasons[0] if available_seasons else ""))
    )
    history = [
        row
        for row in all_rows
        if str(row.get("season_name") or "").strip() == selected_dimension_season
    ]
    if not selected_dimension_season or not history:
        return {"available": False, "reason": "当前赛季暂无维度数据。"}
    season_summaries = {
        item: summarize_dimension_rows(
            [row for row in all_rows if str(row.get("season_name") or "").strip() == item]
        )
        for item in available_seasons
    }
    summary = season_summaries[selected_dimension_season]
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    latest = history[0]
    current_team_name = (
        team_lookup.get(latest.get("team_id"), {}).get("name")
        or str(latest.get("team_name") or "").strip()
        or "未知战队"
    )
    avg_points_by_season = {
        item: safe_rate(
            season_summaries[item].get("daily_points", 0.0),
            season_summaries[item].get("games_played", 0.0),
        )
        for item in available_seasons
    }
    max_avg_points = max(avg_points_by_season.values(), default=0.0) or 1.0
    avg_points = avg_points_by_season[selected_dimension_season]
    radar = [
        {
            "label": "总胜率",
            "ratio": safe_rate(summary.get("wins", 0.0), summary.get("games_played", 0.0)),
            "display": format_pct(safe_rate(summary.get("wins", 0.0), summary.get("games_played", 0.0))),
        },
        {
            "label": "好人胜率",
            "ratio": safe_rate(summary.get("villager_wins", 0.0), summary.get("villager_games", 0.0)),
            "display": format_pct(safe_rate(summary.get("villager_wins", 0.0), summary.get("villager_games", 0.0))),
        },
        {
            "label": "狼人胜率",
            "ratio": safe_rate(summary.get("werewolf_wins", 0.0), summary.get("werewolf_games", 0.0)),
            "display": format_pct(safe_rate(summary.get("werewolf_wins", 0.0), summary.get("werewolf_games", 0.0))),
        },
        {
            "label": "场均积分",
            "ratio": min(avg_points / max_avg_points, 1.0),
            "display": format_dimension_metric_value(avg_points),
        },
        {
            "label": "投狼率",
            "ratio": safe_rate(summary.get("vote_wolf_count", 0.0), summary.get("vote_count", 0.0)),
            "display": format_pct(safe_rate(summary.get("vote_wolf_count", 0.0), summary.get("vote_count", 0.0))),
        },
        {
            "label": "MVP率",
            "ratio": safe_rate(summary.get("mvp_count", 0.0), summary.get("games_played", 0.0)),
            "display": format_pct(safe_rate(summary.get("mvp_count", 0.0), summary.get("games_played", 0.0))),
        },
    ]
    return {
        "available": True,
        "selected_season": selected_dimension_season,
        "available_seasons": available_seasons,
        "current_team_name": current_team_name,
        "summary_cards": [
            {"label": "当前战队", "value": current_team_name},
            {"label": "赛季总维度积分", "value": format_dimension_metric_value(summary.get("daily_points", 0))},
            {"label": "局数 / 胜场", "value": f"{format_dimension_metric_value(summary.get('games_played', 0))} / {format_dimension_metric_value(summary.get('wins', 0))}"},
            {"label": "MVP / SVP / 背锅", "value": f"{format_dimension_metric_value(summary.get('mvp_count', 0))} / {format_dimension_metric_value(summary.get('svp_count', 0))} / {format_dimension_metric_value(summary.get('scapegoat_count', 0))}"},
        ],
        "radar": radar,
        "history": [
            {
                "played_on": str(item.get("played_on") or ""),
                "seat": format_dimension_metric_value(item.get("seat", 0)),
                "team_name": team_lookup.get(item.get("team_id"), {}).get("name", current_team_name),
                "daily_points": format_dimension_metric_value(item.get("daily_points", 0)),
                "games_played": format_dimension_metric_value(item.get("games_played", 0)),
                "wins": format_dimension_metric_value(item.get("wins", 0)),
                "vote_count": format_dimension_metric_value(item.get("vote_count", 0)),
                "vote_wolf_count": format_dimension_metric_value(item.get("vote_wolf_count", 0)),
                "mvp_count": format_dimension_metric_value(item.get("mvp_count", 0)),
                "svp_count": format_dimension_metric_value(item.get("svp_count", 0)),
                "scapegoat_count": format_dimension_metric_value(item.get("scapegoat_count", 0)),
            }
            for item in history
        ],
    }


def build_player_api_payload(ctx: RequestContext, player_id: str) -> dict[str, Any]:
    return _serialize_player_detail_payload(ctx, player_id)


def get_player_legacy_page(ctx: RequestContext, player_id: str, alert: str = "") -> str:
    return legacy.get_player_page(ctx, player_id, alert)


def handle_player_api(ctx: RequestContext, start_response, player_id: str):
    if ctx.method != "GET":
        return start_response_json(
            start_response,
            "405 Method Not Allowed",
            {"error": "player api only supports GET"},
            headers=[("Allow", "GET")],
        )
    payload = build_player_api_payload(ctx, player_id)
    status = "404 Not Found" if payload.get("not_found") else "200 OK"
    return start_response_json(start_response, status, payload)
