from __future__ import annotations

import json

import web_app as legacy

Any = legacy.Any
DEFAULT_TEAM_LOGO = legacy.DEFAULT_TEAM_LOGO
DEFAULT_PLAYER_PHOTO = legacy.DEFAULT_PLAYER_PHOTO
account_role_label = legacy.account_role_label
china_now_label = legacy.china_now_label
DEFAULT_AI_DAILY_BRIEF_MODEL = legacy.DEFAULT_AI_DAILY_BRIEF_MODEL
RequestContext = legacy.RequestContext
RESULT_OPTIONS = legacy.RESULT_OPTIONS
STAGE_OPTIONS = legacy.STAGE_OPTIONS
build_competition_switcher = legacy.build_competition_switcher
build_match_day_path = legacy.build_match_day_path
build_player_rows = legacy.build_player_rows
build_scoped_path = legacy.build_scoped_path
build_team_dimension_panel = legacy.build_team_dimension_panel
build_team_logo_html = legacy.build_team_logo_html
build_team_match_player_score_section = legacy.build_team_match_player_score_section
build_team_rows = legacy.build_team_rows
can_manage_matches = legacy.can_manage_matches
can_manage_team = legacy.can_manage_team
escape = legacy.escape
format_pct = legacy.format_pct
form_value = legacy.form_value
get_guild_by_id = legacy.get_guild_by_id
get_match_competition_name = legacy.get_match_competition_name
get_selected_competition = legacy.get_selected_competition
get_selected_season = legacy.get_selected_season
get_team_captain_id = legacy.get_team_captain_id
get_team_scope = legacy.get_team_scope
get_team_season_status = legacy.get_team_season_status
get_team_season_status_label = legacy.get_team_season_status_label
get_team_stage_group_map = legacy.get_team_stage_group_map
get_user_player = legacy.get_user_player
get_user_team_for_scope = legacy.get_user_team_for_scope
is_admin_user = legacy.is_admin_user
layout = legacy.layout
list_seasons = legacy.list_seasons
load_ai_daily_brief_settings = legacy.load_ai_daily_brief_settings
load_ai_team_season_summary = legacy.load_ai_team_season_summary
load_membership_requests = legacy.load_membership_requests
load_validated_data = legacy.load_validated_data
quote = legacy.quote
render_ai_daily_brief_html = legacy.render_ai_daily_brief_html
resolve_team_player_ids = legacy.resolve_team_player_ids
start_response_json = legacy.start_response_json
summarize_team_match = legacy.summarize_team_match
team_scope_label = legacy.team_scope_label
urlencode = legacy.urlencode


def _build_team_legacy_href(
    team_id: str,
    selected_competition: str | None,
    selected_season: str | None,
) -> str:
    return build_scoped_path(
        f"/teams/{team_id}/legacy",
        selected_competition,
        selected_season if selected_competition else None,
    )


def _build_team_page_payload(ctx: RequestContext, team_id: str) -> dict[str, Any]:
    data = load_validated_data()
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    player_lookup = {player["player_id"]: player for player in data["players"]}
    team = team_lookup.get(team_id)
    if not team:
        return {
            "not_found": True,
            "title": "未找到战队",
            "body_html": '<div class="alert alert-danger">没有找到对应的战队。</div>',
            "legacy_href": f"/teams/{team_id}/legacy",
        }

    current_player = get_user_player(data, ctx.current_user)
    can_manage_team_profile = can_manage_team(ctx, team, current_player)
    can_delete_team = bool(ctx.current_user and is_admin_user(ctx.current_user))
    team_competition_name, team_season_name = get_team_scope(team)
    team_status = get_team_season_status(data, team)
    team_status_label = get_team_season_status_label(team_status)
    can_edit_team_page = can_manage_team_profile and team_status in {"ongoing", "upcoming", "unknown"}
    guild = get_guild_by_id(data, str(team.get("guild_id") or "").strip())
    stage_group_map = get_team_stage_group_map(team)
    team_logo_html = build_team_logo_html(team["logo"], team["name"])
    captain_player = player_lookup.get(get_team_captain_id(team) or "")
    captain_label = captain_player["display_name"] if captain_player else ""
    is_unclaimed = not captain_player
    scope_player, scope_team = get_user_team_for_scope(
        data,
        ctx.current_user,
        team_competition_name,
        team_season_name,
    )
    has_scope_claim_conflict = bool(scope_player and scope_team and scope_team["team_id"] != team_id)
    has_same_team_identity = bool(scope_player and scope_team and scope_team["team_id"] == team_id)
    current_claim_request = (
        next(
            (
                item
                for item in load_membership_requests()
                if ctx.current_user
                and item.get("username") == ctx.current_user["username"]
                and item.get("request_type") == "team_claim"
            ),
            None,
        )
        if ctx.current_user
        else None
    )

    requested_competition = form_value(ctx.query, "competition").strip()
    requested_season = form_value(ctx.query, "season").strip()
    current_team_path = build_scoped_path(
        f"/teams/{team_id}",
        requested_competition or team_competition_name or None,
        requested_season or team_season_name or None,
    )

    claim_panel = ""
    if is_unclaimed and team_status != "completed":
        claim_copy = "战队名称和成员由赛季档案维护。认领后，你可以编辑战队队标、简称、介绍和赛段分组信息。"
        claim_action_html = ""
        if not ctx.current_user:
            claim_action_html = f'<a class="btn btn-dark" href="/login?next={quote(current_team_path)}">登录后申请认领</a>'
        elif has_scope_claim_conflict:
            claim_copy = "当前账号在这个赛事赛季里已经绑定了其他战队身份，不能重复认领新的战队。"
            claim_action_html = '<span class="chip">当前账号已绑定其他战队</span>'
        elif current_claim_request:
            claim_copy = "你当前已经有一条待处理的战队认领申请，处理完成前不能再提交新的申请。"
            claim_action_html = '<a class="btn btn-outline-dark" href="/team-center">前往认领中心查看</a>'
        else:
            if has_same_team_identity:
                claim_copy = "当前账号已经绑定了这支战队的赛季参赛身份。认领通过后会直接把这个赛季身份设为负责人，不会再额外创建队员。"
            claim_action_html = f"""
            <form method="post" action="/team-center" class="m-0">
              <input type="hidden" name="action" value="request_team_claim">
              <input type="hidden" name="team_id" value="{escape(team_id)}">
              <input type="hidden" name="next" value="{escape(current_team_path)}">
              <button type="submit" class="btn btn-dark">申请认领</button>
            </form>
            """
        claim_panel = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3">
            <div>
              <h2 class="section-title mb-2">认领这支战队</h2>
              <p class="section-copy mb-0">{escape(claim_copy)}</p>
            </div>
            {claim_action_html}
          </div>
        </section>
        """

    stage_group_summary = (
        " / ".join(
            f"{stage_label} {escape(stage_group_map.get(stage_key, ''))}"
            for stage_key, stage_label in STAGE_OPTIONS.items()
            if stage_group_map.get(stage_key)
        )
        or "暂未设置"
    )
    stage_group_inputs_html = "".join(
        f"""
        <div class="col-12 col-md-6 col-xl-4">
          <label class="form-label">{escape(stage_label)}</label>
          <input class="form-control" name="stage_group_{escape(stage_key)}" value="{escape(stage_group_map.get(stage_key, ''))}" placeholder="例如 A组 / 淘汰组 / 种子组">
        </div>
        """
        for stage_key, stage_label in STAGE_OPTIONS.items()
    )
    team_manage_panel = f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">战队维护</h2>
          <p class="section-copy mb-0">这里只保留维护操作。战队展示信息已经合并到上方巡礼区域。</p>
        </div>
      </div>
      <div class="form-panel p-3 p-lg-4">
        {(
          f'''
          <form method="post" action="/teams/{escape(team_id)}/logo" enctype="multipart/form-data" class="mb-4">
            <input type="hidden" name="next" value="{escape(current_team_path)}">
            <div class="row g-3 align-items-end">
              <div class="col-12 col-lg-8">
                <input class="form-control" name="logo_file" type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.svg,image/*">
              </div>
              <div class="col-12 col-lg-4 d-flex gap-2">
                <button type="submit" class="btn btn-dark">更新队标</button>
              </div>
            </div>
          </form>
          '''
          if can_edit_team_page
          else ''
        )}
        {(
          f'''
          <form method="post" action="/team-center" class="mb-4">
            <input type="hidden" name="action" value="delete_team">
            <input type="hidden" name="team_id" value="{escape(team_id)}">
            <button type="submit" class="btn btn-outline-danger">管理员删除战队</button>
          </form>
          '''
          if can_delete_team
          else ''
        )}
        {(
          f'''
          <form method="post" action="/team-center">
            <input type="hidden" name="action" value="update_team_profile">
            <input type="hidden" name="team_id" value="{escape(team_id)}">
            <input type="hidden" name="next" value="{escape(current_team_path)}">
            <div class="row g-3">
              <div class="col-12 col-lg-4">
                <label class="form-label">战队简称</label>
                <input class="form-control" name="short_name" value="{escape(team.get('short_name') or '')}" maxlength="24">
              </div>
              <div class="col-12">
                <label class="form-label">战队介绍</label>
                <textarea class="form-control" name="notes" rows="4">{escape(team.get('notes') or '')}</textarea>
              </div>
            </div>
            <button type="submit" class="btn btn-dark mt-4">保存战队资料</button>
          </form>
          '''
          if can_edit_team_page
          else (
            '<div class="small text-secondary">当前赛季已结束，战队资料已锁定。</div>'
            if team_status == "completed"
            else '<div class="small text-secondary">只有管理员、具备战队管理权限的账号或已认领该战队的负责人可以编辑战队资料。</div>'
          )
        )}
        {(
          f'''
          <form method="post" action="/team-center" class="mt-3">
            <input type="hidden" name="action" value="unbind_team_claim">
            <input type="hidden" name="team_id" value="{escape(team_id)}">
            <input type="hidden" name="next" value="{escape(current_team_path)}">
            <button type="submit" class="btn btn-outline-danger">解除当前认领</button>
            <div class="small text-secondary mt-2">只会解除负责人身份，不会删除战队档案，也不会移除赛季成员记录。</div>
          </form>
          '''
          if can_manage_team_profile and not is_unclaimed
          else ''
        )}
        <div class="small text-secondary mt-4">
          <strong>赛段分组：</strong>
          {stage_group_summary}
        </div>
        {(
          f'''
          <form method="post" action="/team-center" class="mt-3">
            <input type="hidden" name="action" value="update_team_stage_groups">
            <input type="hidden" name="team_id" value="{escape(team_id)}">
            <div class="row g-3">
              {stage_group_inputs_html}
            </div>
            <button type="submit" class="btn btn-outline-dark mt-3">保存赛段分组</button>
          </form>
          '''
          if can_edit_team_page
          else ''
        )}
      </div>
    </section>
    """

    team_matches = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
            reverse=True,
        )
        if any(entry["team_id"] == team_id for entry in match["players"])
    ]
    team_competition_names: list[str] = []
    for match in team_matches:
        competition_name = get_match_competition_name(match)
        if competition_name not in team_competition_names:
            team_competition_names.append(competition_name)
    if team_competition_name and team_competition_name not in team_competition_names:
        team_competition_names.append(team_competition_name)

    selected_competition = (
        requested_competition
        or team_competition_name
        or get_selected_competition(ctx, team_competition_names)
    )
    season_names = [team_season_name] if team_season_name else (
        list_seasons(
            {
                "matches": [
                    match
                    for match in team_matches
                    if get_match_competition_name(match) == selected_competition
                ]
            },
            selected_competition,
        )
        if selected_competition
        else []
    )
    selected_season = team_season_name or get_selected_season(ctx, season_names)
    team_dimension_panel = build_team_dimension_panel(
        ctx,
        data,
        team_id,
        selected_competition,
        selected_season,
    )
    competition_switcher = build_competition_switcher(
        f"/teams/{team_id}",
        team_competition_names,
        selected_competition,
        tone="light",
        all_label="比赛总览",
    )
    season_switcher = ""
    competition_groups: dict[str, list[dict[str, Any]]] = {}
    for match in team_matches:
        competition_name = get_match_competition_name(match)
        competition_groups.setdefault(competition_name, []).append(
            summarize_team_match(team_id, match, team_lookup)
        )
    team_match_player_score_section = build_team_match_player_score_section(
        ctx,
        data,
        team_id,
        player_lookup,
        team_lookup,
        selected_competition,
        selected_season or "",
    )
    legacy_href = _build_team_legacy_href(team_id, selected_competition, selected_season)

    if not selected_competition:
        competition_cards = []
        for competition_name in team_competition_names:
            competition_team_stats = {
                row["team_id"]: row for row in build_team_rows(data, competition_name)
            }.get(team_id)
            matches = competition_groups.get(competition_name, [])
            if not competition_team_stats:
                continue
            competition_cards.append(
                f"""
                <div class="col-12 col-md-6">
                  <a class="team-link-card shadow-sm p-4 h-100" href="/teams/{escape(team_id)}?{urlencode({'competition': competition_name})}">
                    <div class="small text-secondary mb-2">比赛入口</div>
                    <h2 class="h4 mb-2">{escape(competition_name)}</h2>
                    <div class="small-muted mb-3">赛季 {escape('、'.join(list_seasons({'matches': team_matches}, competition_name, include_non_ongoing=True)) or '未设置')} · 对局 {competition_team_stats['matches_represented']} 场 · 队员 {competition_team_stats['player_count']} 名</div>
                    <div class="row g-3">
                      <div class="col-6"><div class="small text-secondary">胜率</div><div class="fw-semibold">{format_pct(competition_team_stats['win_rate'])}</div></div>
                      <div class="col-6"><div class="small text-secondary">总积分</div><div class="fw-semibold">{competition_team_stats['points_earned_total']:.2f}</div></div>
                    </div>
                  </a>
                </div>
                """
            )

        body = f"""
        <section class="hero p-4 p-md-5 shadow-lg mb-4">
          <div class="hero-layout">
            <div>
              <div class="eyebrow mb-3">战队比赛总览</div>
              <h1 class="display-6 fw-semibold mb-2">{escape(team['name'])}</h1>
              <p class="mb-2 opacity-75">{escape(team_scope_label(team))}</p>
              <p class="mb-2 opacity-75">简称：{escape(team.get('short_name') or '未设置')}</p>
              <p class="mb-2 opacity-75">负责人：{escape(captain_label or '暂未认领')}</p>
              <p class="mb-2 opacity-75">赛段分组：{stage_group_summary}</p>
              <p class="mb-0 opacity-75">{escape(team['notes'])}</p>
              <div class="d-flex flex-wrap gap-2 mt-3">
                {f'<a class="chip" href="/guilds/{escape(guild["guild_id"])}">{escape(guild["name"])}</a>' if guild else '<span class="chip">未加入门派</span>'}
              </div>
              <div class="d-flex flex-wrap gap-2 mt-3">{competition_switcher}</div>
              <div class="d-flex flex-wrap gap-2 mt-3">
                <a class="btn btn-outline-dark" href="{escape(legacy_href)}">打开旧版团队页</a>
              </div>
            </div>
            <div class="ms-lg-auto">
              {team_logo_html}
            </div>
          </div>
        </section>
        {claim_panel}
        {team_manage_panel if (can_edit_team_page or can_delete_team or can_manage_team_profile) else ''}
        {team_dimension_panel}
        {team_match_player_score_section}
        <section class="panel shadow-sm p-3 p-lg-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">请选择系列赛</h2>
              <p class="section-copy mb-0">战队战绩和排名只在单个系列赛的具体赛季里统计。先选系列赛，再继续切换赛季查看这支战队的队员和战绩。</p>
            </div>
            <a class="btn btn-outline-dark" href="/competitions">返回比赛列表</a>
          </div>
          <div class="row g-3 g-lg-4">{''.join(competition_cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">这支战队暂时还没有比赛数据。</div></div>'}</div>
        </section>
        """
        return {
            "title": f"{team['name']} 页面",
            "body_html": body,
            "legacy_href": legacy_href,
        }

    player_rows = {
        row["player_id"]: row
        for row in build_player_rows(data, selected_competition, selected_season)
    }
    team_rows = {
        row["team_id"]: row for row in build_team_rows(data, selected_competition, selected_season)
    }
    roster_player_ids = resolve_team_player_ids(
        data, team_id, selected_competition, selected_season
    )
    roster_count = len(roster_player_ids)
    team_stats = team_rows.get(
        team_id,
        {
            "team_id": team_id,
            "win_rate": 0.0,
            "stance_rate": 0.0,
            "points_earned_total": 0.0,
            "player_count": roster_count,
            "matches_represented": 0,
        },
    )
    players = []
    for player_id in roster_player_ids:
        player = player_lookup.get(player_id)
        player_stats = player_rows.get(player_id)
        if not player:
            continue
        players.append(
            {
                **player,
                "win_rate": format_pct(player_stats["win_rate"]) if player_stats else "0.0%",
                "stance_rate": format_pct(player_stats["stance_rate"]) if player_stats else "0.0%",
                "points_total": f"{player_stats['points_earned_total']:.2f}" if player_stats else "0.00",
                "games_played": player_stats["games_played"] if player_stats else 0,
                "average_points": player_stats["average_points"] if player_stats else 0.0,
                "has_stats": bool(player_stats),
            }
        )
    players.sort(
        key=lambda item: (
            0 if item["has_stats"] else 1,
            -float(item["points_total"]),
            -item["games_played"],
            item["display_name"],
        )
    )
    ai_team_season_summary = (
        load_ai_team_season_summary(team_id, selected_competition, selected_season)
        if selected_competition and selected_season
        else None
    )
    ai_settings = load_ai_daily_brief_settings()
    ai_configured = bool(ai_settings.get("base_url") and ai_settings.get("api_key"))
    ai_team_summary_actions = ""
    ai_team_summary_admin_editor = ""
    if selected_competition and selected_season:
        if ai_configured and (not ai_team_season_summary or is_admin_user(ctx.current_user)):
            ai_team_summary_actions = f"""
            <form method="post" action="/teams/{escape(team_id)}" class="m-0">
              <input type="hidden" name="action" value="generate_ai_team_season_summary">
              <input type="hidden" name="competition_name" value="{escape(selected_competition)}">
              <input type="hidden" name="season_name" value="{escape(selected_season)}">
              <button type="submit" class="btn btn-dark">{'重生成 AI 战队赛季总结' if ai_team_season_summary else '生成 AI 战队赛季总结'}</button>
            </form>
            """
        elif not ai_configured and is_admin_user(ctx.current_user):
            ai_team_summary_actions = '<a class="btn btn-outline-dark" href="/accounts">前往账号管理配置 AI 接口</a>'
        if ai_team_season_summary and is_admin_user(ctx.current_user):
            ai_team_summary_admin_editor = f"""
            <div class="form-panel p-3 p-lg-4 mt-4">
              <h3 class="h5 mb-2">管理员编辑总结</h3>
              <p class="section-copy mb-3">可以直接修改当前总结正文。保存后会立即覆盖展示内容。</p>
              <form method="post" action="/teams/{escape(team_id)}">
                <input type="hidden" name="action" value="save_ai_team_season_summary">
                <input type="hidden" name="competition_name" value="{escape(selected_competition)}">
                <input type="hidden" name="season_name" value="{escape(selected_season)}">
                <div class="mb-3">
                  <textarea class="form-control" name="summary_content" rows="12">{escape(ai_team_season_summary.get('content') or '')}</textarea>
                </div>
                <div class="d-flex flex-wrap gap-2">
                  <button type="submit" class="btn btn-outline-dark">保存人工编辑</button>
                </div>
              </form>
            </div>
            """
    ai_team_summary_panel = ""
    if selected_season:
        ai_team_summary_panel = (
            f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
                <div>
                  <h2 class="section-title mb-2">AI 战队赛季总结</h2>
                  <p class="section-copy mb-0">基于当前战队在这个赛事赛季下的真实战绩、队员数据和比赛记录生成总结。首次生成对所有访客开放；生成后仅管理员可重生成或编辑。</p>
                </div>
                <div class="d-flex flex-wrap gap-2">{ai_team_summary_actions}</div>
              </div>
              <div class="small text-secondary mb-3">生成时间 {escape(ai_team_season_summary.get('generated_at') or '未生成')} · 模型 {escape(ai_team_season_summary.get('model') or ai_settings.get('model') or DEFAULT_AI_DAILY_BRIEF_MODEL)}</div>
              <div class="editorial-copy mb-0">{render_ai_daily_brief_html(ai_team_season_summary.get('content') or '')}</div>
              {ai_team_summary_admin_editor}
            </section>
            """
            if ai_team_season_summary
            else f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3">
                <div>
                  <h2 class="section-title mb-2">AI 战队赛季总结</h2>
                  <p class="section-copy mb-0">{escape('当前赛季还没有生成 AI 总结，首次生成对所有访客开放。' if ai_configured else '当前还没有配置 AI 接口。配置后即可在这里生成战队赛季总结。')}</p>
                </div>
                <div class="d-flex flex-wrap gap-2">{ai_team_summary_actions}</div>
              </div>
            </section>
            """
        )

    team_short_label = str(team.get("short_name") or team["name"]).strip() or team["name"]
    team_record = f"{team_stats.get('wins', 0)}-{team_stats.get('losses', 0)}"
    team_points_total = f"{float(team_stats.get('points_earned_total', 0.0)):.2f}"
    team_points_per_match = f"{float(team_stats.get('points_per_match', 0.0)):.2f}"
    team_win_display = format_pct(team_stats.get("win_rate", 0.0))
    team_rank_copy = (
        f"当前赛季积分榜第 {team_stats.get('points_rank', '-')} 名 · 战绩 {team_record}"
        if team_stats.get("matches_represented")
        else "当前赛季还没有形成有效积分排名"
    )
    team_win_width = max(0.0, min(100.0, float(team_stats.get("win_rate", 0.0)) * 100.0))
    team_point_speed_width = max(
        0.0,
        min(100.0, float(team_stats.get("points_per_match", 0.0)) / 12.0 * 100.0),
    )
    scoped_match_summaries = [
        summarize_team_match(team_id, match, team_lookup)
        for match in team_matches
        if get_match_competition_name(match) == selected_competition
        and (not selected_season or str(match.get("season") or "").strip() == selected_season)
    ]
    roster_cards_html = "".join(
        f"""
        <a class="team-roster-card text-decoration-none" href="{escape(build_scoped_path('/players/' + player['player_id'], selected_competition, selected_season))}">
          <div class="team-roster-top">
            <div>
              <div class="team-roster-name">{escape(player["display_name"])}</div>
              <div class="team-roster-meta">{escape('赛季主力轮换' if player["has_stats"] else '赛季档案已创建，等待补录数据')}</div>
            </div>
            <div class="team-roster-value">{escape(player["points_total"])} 分</div>
          </div>
          <div class="team-roster-tags">
            {'<span class="player-stat-pill">负责人</span>' if captain_player and captain_player.get("player_id") == player["player_id"] else ''}
            <span class="player-stat-pill">出场 {player["games_played"]}</span>
            <span class="player-stat-pill">胜率 {escape(player["win_rate"])}</span>
            <span class="player-stat-pill">场均 {player["average_points"]:.2f}</span>
          </div>
        </a>
        """
        for player in players[:6]
    ) or """
        <article class="team-roster-card">
          <div class="team-roster-name">暂无赛季阵容数据</div>
          <div class="team-roster-meta mt-2">当前统计口径下，这支战队还没有参赛队员数据。</div>
        </article>
    """
    recent_match_cards: list[str] = []
    for item in scoped_match_summaries[:4]:
        match_detail_path = (
            f"/matches/{item['match_id']}?next="
            f"{quote(build_scoped_path('/teams/' + team_id, selected_competition, selected_season))}"
        )
        day_path = build_match_day_path(
            item["played_on"],
            build_scoped_path("/teams/" + team_id, selected_competition, selected_season),
        )
        match_row = next(
            (
                match
                for match in team_matches
                if match["match_id"] == item["match_id"]
            ),
            None,
        )
        team_result_value = next(
            (
                str(entry.get("result") or "").strip()
                for entry in (match_row or {}).get("players", [])
                if str(entry.get("team_id") or "").strip() == team_id
                and str(entry.get("result") or "").strip()
            ),
            "",
        )
        team_result_label = (
            RESULT_OPTIONS.get(team_result_value, "")
            or (
                "胜利"
                if item["team_score"] > item["opponent_score"]
                else ("失利" if item["team_score"] < item["opponent_score"] else "战平")
            )
        )
        team_award_labels = [
            label
            for label, award_player_id in [
                ("MVP", str((match_row or {}).get("mvp_player_id") or "").strip()),
                ("SVP", str((match_row or {}).get("svp_player_id") or "").strip()),
                ("背锅", str((match_row or {}).get("scapegoat_player_id") or "").strip()),
            ]
            if award_player_id
            and any(
                str(entry.get("team_id") or "").strip() == team_id
                and str(entry.get("player_id") or "").strip() == award_player_id
                for entry in (match_row or {}).get("players", [])
            )
        ]
        team_award_pills = "".join(
            f'<span class="player-stat-pill">{escape(label)}</span>'
            for label in team_award_labels
        ) or '<span class="player-stat-pill">无特殊奖励</span>'
        team_player_score_pills = "".join(
            f'<span class="player-stat-pill">{escape(player_lookup.get(str(entry.get("player_id") or "").strip(), {}).get("display_name", str(entry.get("player_name") or entry.get("player_id") or "未命名队员")))} {float(entry.get("points_earned") or 0.0):.2f}</span>'
            for entry in sorted(
                [
                    participant
                    for participant in (match_row or {}).get("players", [])
                    if str(participant.get("team_id") or "").strip() == team_id
                ],
                key=lambda participant: (
                    -float(participant.get("points_earned") or 0.0),
                    int(participant.get("seat") or 0),
                ),
            )
        ) or '<span class="player-stat-pill">暂无队员得分</span>'
        recent_match_cards.append(
            f"""
            <article class="team-match-card">
              <div class="team-match-top">
                <div>
                  <div class="team-match-name">第 {item["round"]} 轮 · {escape(item["played_on"])}</div>
                  <div class="team-match-meta">{escape(selected_season or item["season"])} · {escape(team_result_label)}</div>
                </div>
                <div class="team-match-value">{item["team_score"]:.2f}</div>
              </div>
              <div class="team-scoreboard">
                <strong>{item["team_score"]:.2f}</strong>
                <span>{escape(team_short_label)} 本队得分</span>
              </div>
              <div class="team-insight-tags">
                {team_player_score_pills}
              </div>
              <div class="team-insight-tags">
                <span class="player-stat-pill">{escape(team_result_label)}</span>
                {team_award_pills}
              </div>
              <div class="team-match-actions">
                <a class="btn btn-sm btn-outline-dark" href="{escape(match_detail_path)}">比赛详情</a>
                <a class="btn btn-sm btn-light border" href="{escape(day_path)}">当日赛程</a>
              </div>
            </article>
            """
        )
    recent_match_cards_html = "".join(recent_match_cards) or """
        <article class="team-match-card">
          <div class="team-match-name">暂无近期比赛</div>
          <div class="team-match-meta mt-2">当前统计口径下，这支战队还没有可展示的赛季比赛记录。</div>
        </article>
    """

    competition_sections = []
    for competition_name, matches in competition_groups.items():
        if competition_name != selected_competition:
            continue
        scoped_matches = [
            item
            for item in matches
            if not selected_season or item["season"] == selected_season
        ]
        rows = []
        for item in sorted(
            scoped_matches,
            key=lambda row: (row["played_on"], row["round"], row["game_no"]),
        ):
            match_detail_path = (
                f"/matches/{item['match_id']}?next="
                f"{quote(build_scoped_path('/teams/' + team_id, selected_competition, selected_season))}"
            )
            day_path = build_match_day_path(
                item["played_on"],
                build_scoped_path("/teams/" + team_id, selected_competition, selected_season),
            )
            manage_actions = (
                f'<a class="btn btn-sm btn-outline-dark" href="/matches/{escape(item["match_id"])}/edit?next={quote(build_scoped_path("/teams/" + team_id, selected_competition, selected_season))}">编辑比赛</a>'
                if can_edit_team_page and can_manage_matches(ctx.current_user, data, selected_competition)
                else ""
            )
            rows.append(
                f"""
                <tr>
                  <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(match_detail_path)}">{escape(item['match_id'])}</a></td>
                  <td>{escape(item['season'])}</td>
                  <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(day_path)}">{escape(item['played_on'])}</a></td>
                  <td>{escape(item['stage'])}</td>
                  <td>第 {item['round']} 轮</td>
                  <td>{escape(item['table_label'])}</td>
                  <td>{escape(item['format'])}</td>
                  <td>{escape(item['winning_camp'])}</td>
                  <td>{item['team_score']:.2f}</td>
                  <td>{item['opponent_score']:.2f}</td>
                  <td>{item['duration_minutes']} 分钟</td>
                  <td>
                    <a class="btn btn-sm btn-outline-dark" href="{escape(match_detail_path)}">详情</a>
                    {manage_actions}
                  </td>
                </tr>
                """
            )
        competition_sections.append(
            f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
                <div>
                  <h2 class="section-title mb-2">{escape(competition_name)}</h2>
                  <p class="section-copy mb-0">当前赛季：{escape(selected_season or '全部赛季')}。这里展示 {escape(team['name'])} 在该系列赛当前赛季中的全部比赛。</p>
                </div>
              </div>
              <div class="table-responsive">
                <table class="table align-middle">
                  <thead>
                    <tr>
                      <th>编号</th>
                      <th>赛季</th>
                      <th>日期</th>
                      <th>阶段</th>
                      <th>轮次</th>
                      <th>房间</th>
                      <th>板型</th>
                      <th>胜利阵营</th>
                      <th>{escape(team['short_name'])} 得分</th>
                      <th>对手得分</th>
                      <th>时长</th>
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

    guild_options_html = "".join(
        f'<option value="{escape(item["guild_id"])}">{escape(item["name"])}</option>'
        for item in sorted(data.get("guilds", []), key=lambda row: row["name"])
    )
    guild_panel = ""
    if guild:
        guild_panel = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <h2 class="section-title mb-2">关联门派</h2>
          <p class="section-copy mb-3">这支战队已经加入门派，门派页会统一汇总它在不同赛事与赛季中的荣誉和公开成绩。</p>
          <a class="btn btn-outline-dark" href="/guilds/{escape(guild['guild_id'])}">{escape(guild['name'])}</a>
        </section>
        """
    elif can_edit_team_page and guild_options_html:
        guild_panel = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <h2 class="section-title mb-2">申请加入门派</h2>
          <p class="section-copy mb-4">当前赛季战队还没有门派归属。管理员、具备战队管理权限的账号或已认领该战队的负责人可以从这里向某个门派提交加入申请，等待门主或门派管理员审核。</p>
          <form method="post" action="/guilds">
            <input type="hidden" name="action" value="request_team_guild_join">
            <input type="hidden" name="team_id" value="{escape(team_id)}">
            <div class="mb-4">
              <label class="form-label">选择门派</label>
              <select class="form-select" name="guild_id">{guild_options_html}</select>
            </div>
            <button type="submit" class="btn btn-dark">提交申请</button>
          </form>
        </section>
        """

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">战队巡礼</div>
          <h1 class="display-6 fw-semibold mb-2">{escape(team['name'])}</h1>
          <p class="mb-2 opacity-75">{escape(team_scope_label(team))}</p>
          <p class="mb-2 opacity-75">简称：{escape(team.get('short_name') or '未设置')}</p>
          <p class="mb-2 opacity-75">负责人：{escape(captain_label or '暂未认领')}</p>
          <p class="mb-2 opacity-75">赛段分组：{stage_group_summary}</p>
          <p class="mb-0 opacity-75">{escape(team['notes'])}</p>
          <div class="d-flex flex-wrap gap-2 mt-3">
            <span class="chip">{escape(team_status_label)}</span>
            <span class="chip">{'待认领' if is_unclaimed else f'负责人：{escape(captain_label)}'}</span>
            {f'<a class="chip" href="/guilds/{escape(guild["guild_id"])}">关联门派：{escape(guild["name"])}</a>' if guild else '<span class="chip">未加入门派</span>'}
          </div>
          <div class="d-flex flex-wrap gap-2 mt-3">{competition_switcher}</div>
          {f'<div class="d-flex flex-wrap gap-2 mt-3">{season_switcher}</div>' if season_switcher else ''}
          <div class="d-flex flex-wrap gap-3 mt-3">
            <span class="chip">{escape(selected_season or '当前赛季')}</span>
            <span class="chip">胜率 {format_pct(team_stats['win_rate'])}</span>
            <span class="chip">总积分 {team_stats['points_earned_total']:.2f}</span>
            <span class="chip">队员 {roster_count} 名</span>
            <a class="btn btn-outline-dark" href="{escape(legacy_href)}">旧版团队页</a>
          </div>
        </div>
        <div class="ms-lg-auto">
          {team_logo_html}
        </div>
      </div>
    </section>
    {claim_panel}
    {(
      '<div class="alert alert-secondary mb-4">当前战队所属赛季已结束，战队资料和门派申请入口已关闭，页面仅保留公开展示。</div>'
      if team_status == "completed"
      else ''
    )}
    {ai_team_summary_panel}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">战队赛季主页</h2>
          <p class="section-copy mb-0">把这个赛季最该先看的信息收在一屏里：战绩、阵容、状态和最近比赛走势。</p>
        </div>
      </div>
      <div class="team-showcase-grid">
        <article class="team-showcase-card">
          <div class="eyebrow">Team Dossier</div>
          <div class="team-headline">{escape(team['name'])}</div>
          <div class="team-subtitle">{escape(selected_competition or team_scope_label(team))} · {escape(selected_season or '当前赛季')} · {escape(team_rank_copy)}</div>
          <div class="team-badge-row mt-3">
            <span class="team-badge">{escape(team_status_label)}</span>
            <span class="team-badge">队员 {roster_count} 名</span>
            <span class="team-badge">出赛 {team_stats.get('matches_represented', 0)} 场</span>
            <span class="team-badge">总积分 {team_points_total}</span>
          </div>
          <div class="team-kpi-grid">
            <div class="team-kpi-card">
              <div class="team-kpi-label">Season Record</div>
              <div class="team-kpi-value">{team_record}</div>
              <div class="team-kpi-copy">当前赛季累计胜负走势</div>
            </div>
            <div class="team-kpi-card">
              <div class="team-kpi-label">Win Rate</div>
              <div class="team-kpi-value">{team_win_display}</div>
              <div class="team-kpi-copy">按赛季全部出场计算</div>
            </div>
            <div class="team-kpi-card">
              <div class="team-kpi-label">Points Total</div>
              <div class="team-kpi-value">{team_points_total}</div>
              <div class="team-kpi-copy">赛季累计积分沉淀</div>
            </div>
            <div class="team-kpi-card">
              <div class="team-kpi-label">Points Per Match</div>
              <div class="team-kpi-value">{team_points_per_match}</div>
              <div class="team-kpi-copy">每场比赛的稳定产出</div>
            </div>
            <div class="team-kpi-card">
              <div class="team-kpi-label">Matches Played</div>
              <div class="team-kpi-value">{team_stats.get('matches_represented', 0)}</div>
              <div class="team-kpi-copy">当前赛季有效出赛场次</div>
            </div>
            <div class="team-kpi-card">
              <div class="team-kpi-label">Roster Active</div>
              <div class="team-kpi-value">{team_stats.get('player_count', roster_count)}</div>
              <div class="team-kpi-copy">当前赛季已上场队员数</div>
            </div>
          </div>
        </article>
        <aside class="team-insight-card">
          <div>
            <h3 class="section-title mb-2">赛季观察</h3>
            <p class="section-copy mb-0">先看这支队伍现在是稳扎稳打、靠积分效率拉开，还是靠判断和阵容深度取胜。</p>
          </div>
          <div class="team-meter-row">
            <div class="team-meter-head">
              <strong>胜率表现</strong>
              <span>{team_win_display}</span>
            </div>
            <div class="team-meter-track"><div class="team-meter-fill" style="width: {team_win_width:.1f}%"></div></div>
          </div>
          <div class="team-meter-row">
            <div class="team-meter-head">
              <strong>积分效率</strong>
              <span>场均 {team_points_per_match}</span>
            </div>
            <div class="team-meter-track"><div class="team-meter-fill" style="width: {team_point_speed_width:.1f}%"></div></div>
          </div>
          <div class="team-note-grid">
            <div class="team-note-item">
              <div class="team-note-label">Captain</div>
              <div class="team-note-value">{escape(captain_label or '暂未认领')}</div>
            </div>
            <div class="team-note-item">
              <div class="team-note-label">Guild</div>
              <div class="team-note-value">{escape(guild['name'] if guild else '未加入门派')}</div>
            </div>
            <div class="team-note-item">
              <div class="team-note-label">Stage Group</div>
              <div class="team-note-value">{stage_group_summary}</div>
            </div>
            <div class="team-note-item">
              <div class="team-note-label">Notes</div>
              <div class="team-note-value">{escape(team.get('notes') or '暂无战队备注')}</div>
            </div>
          </div>
        </aside>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-4">
        <div class="col-12 col-xl-6">
          <h2 class="section-title mb-2">赛季阵容</h2>
          <p class="section-copy mb-3">先展示当前赛季最主要的轮换成员，方便从战队页直接下钻到队员档案。</p>
          <div class="team-roster-grid">{roster_cards_html}</div>
        </div>
        <div class="col-12 col-xl-6">
          <h2 class="section-title mb-2">最近比赛</h2>
          <p class="section-copy mb-3">把最近几场的比分和比赛详情提上来，不用先翻到底部的大表。</p>
          <div class="team-match-grid">{recent_match_cards_html}</div>
        </div>
      </div>
    </section>
    {guild_panel}
    {team_dimension_panel}
    {team_match_player_score_section}
    {team_manage_panel if (can_edit_team_page or can_delete_team or can_manage_team_profile) else ''}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">完整比赛明细</h2>
          <p class="section-copy mb-0">下面继续保留完整赛季比赛表，方便你核对每一场的板型、得分和操作入口。</p>
        </div>
      </div>
    </section>
    {''.join(competition_sections) if competition_sections else '<div class="alert alert-secondary">该战队在当前统计口径下暂时没有比赛记录。</div>'}
    """
    return {
        "title": f"{team['name']} 页面",
        "body_html": body,
        "legacy_href": legacy_href,
    }


def build_team_frontend_page(ctx: RequestContext, team_id: str) -> str:
    data = load_validated_data()
    team = next((item for item in data["teams"] if item["team_id"] == team_id), None)
    if not team:
        return layout("未找到战队", '<div class="alert alert-danger">没有找到对应的战队。</div>', ctx)

    requested_competition = form_value(ctx.query, "competition").strip() or None
    requested_season = form_value(ctx.query, "season").strip() or None
    bootstrap = json.dumps(
        {
            "apiEndpoint": f"/api/teams/{team_id}",
            "alert": form_value(ctx.query, "alert").strip(),
            "legacyHref": _build_team_legacy_href(team_id, requested_competition, requested_season),
        },
        ensure_ascii=False,
    )

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#122238">
    <title>{escape(team['name'])} 页面</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;800;900&family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/competitions-app.css">
  </head>
  <body class="competitions-app-shell team-detail-app-shell">
    <div class="shell-backdrop"></div>
    <header class="shell-header">
      <div class="shell-brand">
        <a class="shell-brand-link" href="/dashboard" aria-label="返回赛事首页">
          <span class="shell-brand-mark" aria-hidden="true"></span>
          <span>WOLF</span>
        </a>
        <span class="shell-brand-copy">战队档案 · API Driven</span>
      </div>
      <nav class="shell-nav" aria-label="主导航">
        <a class="shell-nav-link" href="/dashboard">仪表盘</a>
        <a class="shell-nav-link" href="/competitions">比赛中心</a>
        <a class="shell-nav-link is-active" href="/teams">战队</a>
        <a class="shell-nav-link" href="/players">选手</a>
        <a class="shell-nav-link" href="/guilds">门派</a>
        <a class="shell-nav-link" href="/schedule">赛程日历</a>
      </nav>
      {_build_team_account_html(ctx)}
    </header>
    <main id="team-app" class="competitions-layout team-detail-layout" aria-live="polite">
      <section class="competitions-panel competitions-loading-shell">
        <div class="competitions-section-kicker">Loading Team</div>
        <h1 class="competitions-title">正在加载战队详情</h1>
        <p class="competitions-copy">新前端会通过独立 API 拉取战队档案、赛季数据、阵容和最近比赛。</p>
      </section>
    </main>
    <script>window.__WEREWOLF_TEAM_BOOTSTRAP__ = {bootstrap};</script>
    <script src="/assets/team-app.js" defer></script>
  </body>
</html>
"""


def _build_team_account_html(ctx: RequestContext) -> str:
    if ctx.current_user:
        display_name = ctx.current_user.get("display_name") or ctx.current_user["username"]
        return f"""
        <div class="shell-account">
          <span class="shell-account-name">{escape(display_name)}</span>
          <form method="post" action="/logout" class="shell-account-form">
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


def _team_asset_href(path: str | None, fallback: str = DEFAULT_TEAM_LOGO) -> str:
    clean_path = str(path or "").strip() or fallback
    if clean_path.startswith(("http://", "https://", "/")):
        return clean_path
    return f"/{clean_path}"


def _stage_label(stage_key: str) -> str:
    return STAGE_OPTIONS.get(stage_key, stage_key or "未分组")


def _serialize_team_detail_payload(ctx: RequestContext, team_id: str) -> dict[str, Any]:
    data = load_validated_data()
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    player_lookup = {player["player_id"]: player for player in data["players"]}
    team = team_lookup.get(team_id)
    requested_competition = form_value(ctx.query, "competition").strip()
    requested_season = form_value(ctx.query, "season").strip()
    legacy_href = _build_team_legacy_href(team_id, requested_competition or None, requested_season or None)
    if not team:
        return {
            "not_found": True,
            "error": "没有找到对应的战队。",
            "title": "未找到战队",
            "alert": form_value(ctx.query, "alert").strip(),
            "legacy_href": legacy_href,
        }

    team_competition_name, team_season_name = get_team_scope(team)
    selected_competition = requested_competition or team_competition_name or ""
    selected_season = requested_season or team_season_name or ""
    team_status = get_team_season_status(data, team)
    team_status_label = get_team_season_status_label(team_status)
    guild = get_guild_by_id(data, str(team.get("guild_id") or "").strip())
    captain = player_lookup.get(get_team_captain_id(team) or "")
    stage_group_map = get_team_stage_group_map(team)
    stage_groups = [
        {"stage": stage_key, "label": stage_label, "group": str(stage_group_map.get(stage_key) or "").strip()}
        for stage_key, stage_label in STAGE_OPTIONS.items()
        if str(stage_group_map.get(stage_key) or "").strip()
    ]

    scoped_matches = []
    total_points = 0.0
    wins = 0
    player_stats: dict[str, dict[str, Any]] = {}
    for match in data["matches"]:
        if selected_competition and get_match_competition_name(match) != selected_competition:
            continue
        if selected_season and str(match.get("season") or "") != selected_season:
            continue
        team_entries = [entry for entry in match.get("players", []) if entry.get("team_id") == team_id]
        if not team_entries:
            continue
        match_points = sum(float(entry.get("points_earned") or 0) for entry in team_entries)
        match_win = any(entry.get("result") == "win" for entry in team_entries)
        total_points += match_points
        wins += 1 if match_win else 0
        scoped_matches.append(
            {
                "match_id": match.get("match_id") or "",
                "played_on": match.get("played_on") or "",
                "stage": match.get("stage") or "",
                "stage_label": _stage_label(str(match.get("stage") or "")),
                "round": int(match.get("round") or 0),
                "game_no": int(match.get("game_no") or 0),
                "format": match.get("format") or "",
                "winning_camp": match.get("winning_camp") or "",
                "points": round(match_points, 1),
                "result": "胜" if match_win else "负",
                "href": f"/matches/{quote(str(match.get('match_id') or ''))}",
            }
        )
        for entry in team_entries:
            player_id = str(entry.get("player_id") or "").strip()
            if not player_id:
                continue
            stat = player_stats.setdefault(
                player_id,
                {"player_id": player_id, "matches": 0, "wins": 0, "points": 0.0, "roles": {}},
            )
            stat["matches"] += 1
            stat["wins"] += 1 if entry.get("result") == "win" else 0
            stat["points"] += float(entry.get("points_earned") or 0)
            role = str(entry.get("role") or "未记录").strip() or "未记录"
            stat["roles"][role] = stat["roles"].get(role, 0) + 1

    member_ids = [str(item) for item in team.get("members", [])]
    for player in data["players"]:
        if player.get("team_id") == team_id and player["player_id"] not in member_ids:
            member_ids.append(player["player_id"])
    roster = []
    for player_id in member_ids:
        player = player_lookup.get(player_id)
        if not player:
            continue
        stat = player_stats.get(player_id, {"matches": 0, "wins": 0, "points": 0.0, "roles": {}})
        top_role = "-"
        if stat.get("roles"):
            top_role = sorted(stat["roles"].items(), key=lambda item: (-item[1], item[0]))[0][0]
        roster.append(
            {
                "player_id": player_id,
                "name": player.get("display_name") or player_id,
                "photo": _team_asset_href(player.get("photo"), DEFAULT_PLAYER_PHOTO),
                "notes": player.get("notes") or "暂无选手备注",
                "href": f"/players/{quote(player_id)}",
                "matches": int(stat.get("matches") or 0),
                "wins": int(stat.get("wins") or 0),
                "points": round(float(stat.get("points") or 0), 1),
                "win_rate": format_pct((float(stat.get("wins") or 0) / float(stat.get("matches") or 1)) if stat.get("matches") else 0.0),
                "top_role": top_role,
            }
        )

    matches_played = len(scoped_matches)
    losses = max(matches_played - wins, 0)
    points_per_match = (total_points / matches_played) if matches_played else 0.0
    win_width = (wins / matches_played * 100) if matches_played else 0.0
    points_width = max(0.0, min(100.0, (points_per_match / 8.0) * 100.0))
    recent_matches = sorted(
        scoped_matches,
        key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
        reverse=True,
    )[:8]

    competition_href = "/competitions"
    if selected_competition:
        competition_href = f"/competitions?{urlencode({'competition': selected_competition})}"
    current_player = get_user_player(data, ctx.current_user)
    can_manage_team_profile = can_manage_team(ctx, team, current_player)
    manage_href = f"/teams/{quote(team_id)}/legacy?view=manage" if can_manage_team_profile else ""

    return {
        "title": f"{team['name']} 页面",
        "alert": form_value(ctx.query, "alert").strip(),
        "generated_at": china_now_label(),
        "legacy_href": legacy_href,
        "team": {
            "team_id": team_id,
            "name": team.get("name") or team_id,
            "short_name": team.get("short_name") or "",
            "logo": _team_asset_href(team.get("logo")),
            "notes": team.get("notes") or "暂无战队备注",
            "competition": selected_competition or "全部赛事",
            "season": selected_season or "全部赛季",
            "status": team_status,
            "status_label": team_status_label,
            "captain": captain.get("display_name") if captain else "暂未认领",
            "guild": guild.get("name") if guild else "未加入门派",
            "stage_groups": stage_groups,
        },
        "actions": {
            "teams_href": "/teams",
            "competition_href": competition_href,
            "legacy_href": legacy_href,
            "manage_href": manage_href,
        },
        "metrics": [
            {"label": "赛季战绩", "value": f"{wins}-{losses}", "copy": "当前口径胜负"},
            {"label": "总积分", "value": f"{total_points:.1f}", "copy": "当前赛季累计"},
            {"label": "场均积分", "value": f"{points_per_match:.1f}", "copy": "每局稳定产出"},
            {"label": "胜率", "value": format_pct((wins / matches_played) if matches_played else 0.0), "copy": "按已完成比赛"},
            {"label": "出赛局数", "value": str(matches_played), "copy": "有效比赛记录"},
            {"label": "阵容人数", "value": str(len(roster)), "copy": "当前赛季成员"},
        ],
        "insights": {
            "record": f"{wins}-{losses}",
            "win_rate": format_pct((wins / matches_played) if matches_played else 0.0),
            "win_width": round(win_width, 1),
            "points_per_match": f"{points_per_match:.1f}",
            "points_width": round(points_width, 1),
            "stage_summary": " / ".join(f"{item['label']} {item['group']}" for item in stage_groups) or "暂未设置",
        },
        "roster": roster,
        "matches": recent_matches,
    }


def build_team_api_payload(ctx: RequestContext, team_id: str) -> dict[str, Any]:
    return _serialize_team_detail_payload(ctx, team_id)


def get_team_legacy_page(ctx: RequestContext, team_id: str, alert: str = "") -> str:
    return legacy.get_team_page(ctx, team_id, alert)


def handle_team_api(ctx: RequestContext, start_response, team_id: str):
    if ctx.method != "GET":
        return start_response_json(
            start_response,
            "405 Method Not Allowed",
            {"error": "team api only supports GET"},
            headers=[("Allow", "GET")],
        )
    payload = build_team_api_payload(ctx, team_id)
    status = "404 Not Found" if payload.get("not_found") else "200 OK"
    return start_response_json(start_response, status, payload)
