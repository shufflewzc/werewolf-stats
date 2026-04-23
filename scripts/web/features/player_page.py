from __future__ import annotations

import json

import web_app as legacy

Any = legacy.Any
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
format_pct = legacy.format_pct
form_value = legacy.form_value
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
              <div class="eyebrow">Player Dossier</div>
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
            "legacyHref": _build_player_legacy_href(player_id, requested_competition, requested_season),
        },
        ensure_ascii=False,
    )
    body = f"""
    <div id="player-app" aria-live="polite">
      <section class="panel shadow-sm p-3 p-lg-4">
        <div class="small text-secondary">正在加载队员详情，前端会通过独立接口渲染当前筛选范围内容。</div>
      </section>
    </div>
    <script>window.__WEREWOLF_PLAYER_BOOTSTRAP__ = {bootstrap};</script>
    <script src="/assets/player-app.js" defer></script>
    """
    return layout(
        f"{escape(str(player.get('display_name') or player_id))} 页面",
        body,
        ctx,
        alert=form_value(ctx.query, "alert").strip(),
    )


def build_player_api_payload(ctx: RequestContext, player_id: str) -> dict[str, Any]:
    payload = _build_player_page_payload(ctx, player_id)
    payload["alert"] = form_value(ctx.query, "alert").strip()
    return payload


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
