from __future__ import annotations

from html import escape
import secrets
from typing import Any
from urllib.parse import urlencode
import web_app as legacy

RequestContext = legacy.RequestContext
DEFAULT_PLAYER_PHOTO = legacy.DEFAULT_PLAYER_PHOTO
DEFAULT_TEAM_LOGO = legacy.DEFAULT_TEAM_LOGO
SESSIONS = legacy.SESSIONS
SESSION_COOKIE = legacy.SESSION_COOKIE
append_user_player_binding = legacy.append_user_player_binding
build_scoped_path = legacy.build_scoped_path
build_team_serial = legacy.build_team_serial
build_team_scope_value = legacy.build_team_scope_value
build_unique_slug = legacy.build_unique_slug
china_now_label = legacy.china_now_label
china_today_label = legacy.china_today_label
form_value = legacy.form_value
get_guild_by_id = legacy.get_guild_by_id
get_team_by_id = legacy.get_team_by_id
get_team_captain_id = legacy.get_team_captain_id
get_team_for_player = legacy.get_team_for_player
get_team_scope = legacy.get_team_scope
get_team_season_status = legacy.get_team_season_status
get_user_bound_player_ids = legacy.get_user_bound_player_ids
get_user_by_player_id = legacy.get_user_by_player_id
get_user_player = legacy.get_user_player
get_user_team_identities = legacy.get_user_team_identities
is_team_captain = legacy.is_team_captain
layout = legacy.layout
list_ongoing_team_scopes = legacy.list_ongoing_team_scopes
load_membership_requests = legacy.load_membership_requests
load_users = legacy.load_users
load_validated_data = legacy.load_validated_data
parse_team_scope_value = legacy.parse_team_scope_value
redirect = legacy.redirect
remove_member_from_team = legacy.remove_member_from_team
revoke_user_sessions = legacy.revoke_user_sessions
save_membership_requests = legacy.save_membership_requests
save_repository_state = legacy.save_repository_state
set_user_primary_player_id = legacy.set_user_primary_player_id
start_response_html = legacy.start_response_html
team_scope_label = legacy.team_scope_label
user_has_match_history = legacy.user_has_match_history
user_has_permission = legacy.user_has_permission
user_has_team_identity_in_scope = legacy.user_has_team_identity_in_scope
validate_team_creation = legacy.validate_team_creation
def get_team_member_removal_error(
    data: dict[str, Any],
    team: dict[str, Any] | None,
    acting_player: dict[str, Any] | None,
    member_player_id: str,
) -> str:
    if not team or not acting_player or not member_player_id:
        return "没有找到要处理的队员。"
    if member_player_id not in team["members"]:
        return "该队员已经不在当前战队中。"
    if get_team_captain_id(team) == member_player_id:
        return "当前队长不能被直接移除。"
    if member_player_id == acting_player["player_id"]:
        return "你不能删除自己。"
    if user_has_match_history(data, member_player_id):
        return "该队员已经有历史比赛记录，不能直接删除，请改用转会。"
    return ""

def get_team_center_page(
    ctx: RequestContext,
    alert: str = "",
    create_values: dict[str, str] | None = None,
    join_values: dict[str, str] | None = None,
) -> str:
    data = load_validated_data()
    requests = load_membership_requests()
    users = load_users()
    current_user = ctx.current_user
    current_player = get_user_player(data, current_user)
    current_team = get_team_for_player(data, current_player)
    teams = sorted(data["teams"], key=lambda item: item["name"])
    create_form = create_values or {"scope": "", "name": "", "short_name": "", "notes": ""}
    join_form = join_values or {"team_id": ""}
    current_request = next(
        (
            item
            for item in requests
            if current_user
            and item["username"] == current_user["username"]
            and item["request_type"] in {"join", "transfer"}
        ),
        None,
    )
    ongoing_scopes = list_ongoing_team_scopes(data)
    user_scope_keys = {
        build_team_scope_value(*get_team_scope(team))
        for _, team in get_user_team_identities(data, current_user)
    }
    create_scope_options = "".join(
        f'<option value="{escape(scope["value"])}"{" selected" if create_form["scope"] == scope["value"] else ""}>{escape(scope["label"])}</option>'
        for scope in ongoing_scopes
        if scope["value"] not in user_scope_keys
    )
    eligible_join_teams = [
        team
        for team in teams
        if build_team_scope_value(*get_team_scope(team)) not in user_scope_keys
        and build_team_scope_value(*get_team_scope(team))
        in {scope["value"] for scope in ongoing_scopes}
    ]
    join_options = "".join(
        f'<option value="{escape(team["team_id"])}"{" selected" if join_form["team_id"] == team["team_id"] else ""}>{escape(team["name"])} · {escape(team_scope_label(team))}</option>'
        for team in eligible_join_teams
    )
    status_rank = {"ongoing": 0, "upcoming": 1, "completed": 2, "unknown": 3}
    status_label_map = {
        "ongoing": "进行中",
        "upcoming": "未开始",
        "completed": "已结束",
        "unknown": "未配置",
    }
    identity_cards = []
    for player, team in sorted(
        get_user_team_identities(data, current_user),
        key=lambda pair: (
            status_rank.get(get_team_season_status(data, pair[1]), 3),
            pair[1].get("competition_name", ""),
            pair[1].get("season_name", ""),
            pair[1]["name"],
        ),
    ):
        team_status = get_team_season_status(data, team)
        guild = get_guild_by_id(data, str(team.get("guild_id") or "").strip())
        guild_html = (
            f'<a class="chip" href="/guilds/{escape(guild["guild_id"])}">{escape(guild["name"])}</a>'
            if guild
            else '<span class="chip">未加入门派</span>'
        )
        current_identity_html = (
            '<span class="chip">当前管理身份</span>'
            if current_player and current_player["player_id"] == player["player_id"]
            else f"""
            <form method="post" action="/team-center" class="m-0">
              <input type="hidden" name="action" value="switch_primary_identity">
              <input type="hidden" name="player_id" value="{escape(player['player_id'])}">
              <button type="submit" class="btn btn-sm btn-outline-dark">切换到这个身份</button>
            </form>
            """
        )
        identity_cards.append(
            f"""
            <div class="col-12 col-xl-6">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div class="card-kicker mb-2">{escape(status_label_map.get(team_status, '未配置'))}</div>
                    <h3 class="h5 mb-1">{escape(team['name'])}</h3>
                    <div class="small-muted">{escape(team_scope_label(team))}</div>
                  </div>
                  <span class="chip">{'队长' if is_team_captain(team, player) else '队员'}</span>
                 </div>
                 <div class="small text-secondary mt-3">当前赛季身份 ID：{escape(player['player_id'])}</div>
                 <div class="d-flex flex-wrap gap-2 mt-2">
                   <span class="small text-secondary align-self-center">所属门派</span>
                   {guild_html}
                 </div>
                 <div class="d-flex flex-wrap gap-2 mt-3">
                   <a class="btn btn-sm btn-dark" href="{escape(build_scoped_path('/teams/' + team['team_id'], *get_team_scope(team)))}">查看战队页</a>
                   <a class="btn btn-sm btn-outline-dark" href="{escape(build_scoped_path('/players/' + player['player_id'], *get_team_scope(team)))}">查看数据页</a>
                   {current_identity_html}
                 </div>
              </div>
            </div>
            """
        )
    identity_panel = f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">我的赛季身份</h2>
          <p class="section-copy mb-0">一个账号可以绑定多个赛季参赛身份。这里会优先展示进行中的赛事身份；如果你要管理别的赛季战队，可以先切换到对应身份。</p>
        </div>
      </div>
      <div class="row g-3">{''.join(identity_cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">当前账号还没有任何赛季战队身份。</div></div>'}</div>
    </section>
    """
    season_team_manage_panel = f"""
    <section class="panel shadow-sm p-3 p-lg-4 mt-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">新赛季战队操作</h2>
          <p class="section-copy mb-0">战队现在按赛季存在。新赛季开始后，可以重新创建一支战队，或者申请加入该赛季现有战队；历史赛季数据会继续保留在旧战队页面里。</p>
        </div>
      </div>
      <div class="row g-4">
        <div class="col-12 col-xl-6">
          <div class="form-panel h-100 p-3 p-lg-4">
            <h3 class="h5 mb-2">创建赛季战队</h3>
            <p class="section-copy mb-4">同一赛事赛季内，账号只能绑定一个参赛身份；不同赛季可以重新创建新的战队。</p>
            {
                f'''
                <form method="post" action="/team-center">
                  <input type="hidden" name="action" value="create_team">
                  <div class="mb-3">
                    <label class="form-label">赛事赛季</label>
                    <select class="form-select" name="team_scope">{create_scope_options}</select>
                  </div>
                  <div class="mb-3">
                    <label class="form-label">战队名称</label>
                    <input class="form-control" name="team_name" value="{escape(create_form['name'])}">
                  </div>
                  <div class="mb-3">
                    <label class="form-label">战队简称</label>
                    <input class="form-control" name="short_name" value="{escape(create_form['short_name'])}">
                  </div>
                  <div class="mb-4">
                    <label class="form-label">战队说明</label>
                    <textarea class="form-control" name="notes" rows="4">{escape(create_form['notes'])}</textarea>
                  </div>
                  <button type="submit" class="btn btn-dark">创建战队</button>
                </form>
                '''
                if create_scope_options
                else '<div class="small text-secondary">当前没有可创建战队的进行中赛季，先让赛事负责人配置赛季档期。</div>'
            }
          </div>
        </div>
        <div class="col-12 col-xl-6">
          <div class="form-panel h-100 p-3 p-lg-4">
            <h3 class="h5 mb-2">申请加入赛季战队</h3>
            <p class="section-copy mb-4">申请通过后，会为你在对应赛季生成新的参赛身份，并自动绑定到当前账号。</p>
            {
                f'''
                <form method="post" action="/team-center">
                  <input type="hidden" name="action" value="request_join">
                  <div class="mb-4">
                    <label class="form-label">选择战队</label>
                    <select class="form-select" name="team_id">{join_options}</select>
                  </div>
                  <button type="submit" class="btn btn-dark">提交加入申请</button>
                </form>
                '''
                if join_options
                else '<div class="small text-secondary">当前没有适合你加入的进行中赛季战队。</div>'
            }
          </div>
        </div>
      </div>
    </section>
    """

    if current_player:
        team_card = ""
        if current_team:
            current_team_guild = get_guild_by_id(data, str(current_team.get("guild_id") or "").strip())
            current_team_guild_html = (
                f'<a class="btn btn-outline-light" href="/guilds/{escape(current_team_guild["guild_id"])}">所属门派：{escape(current_team_guild["name"])}</a>'
                if current_team_guild
                else '<span class="chip">当前未加入门派</span>'
            )
            captain_badge = ""
            if is_team_captain(current_team, current_player):
                captain_badge = '<span class="chip">当前队长</span>'
            pending_transfer = next(
                (
                    item
                    for item in requests
                    if current_user and item["username"] == current_user["username"] and item["request_type"] == "transfer"
                ),
                None,
            )
            leave_hint = (
                "你当前有转会申请正在处理中，请先取消申请或等待审核结果。"
                if pending_transfer
                else (
                    "你有历史比赛记录，当前不支持直接退出战队，请改用转会申请。"
                    if user_has_match_history(data, current_player["player_id"])
                    else "如果你还没有比赛记录，可以直接退出当前战队。"
                )
            )
            transfer_options = "".join(
                f'<option value="{escape(team["team_id"])}">{escape(team["name"])}</option>'
                for team in teams
                if team["team_id"] != current_team["team_id"]
                and get_team_scope(team) == get_team_scope(current_team)
            )
            transfer_panel = (
                f"""
                <div class="form-panel h-100 p-3 p-lg-4">
                  <h2 class="section-title mb-2">申请转会</h2>
                  <p class="section-copy mb-4">转会需要目标战队队长审核通过。</p>
                  <form method="post" action="/team-center">
                    <input type="hidden" name="action" value="request_transfer">
                    <div class="mb-4">
                      <label class="form-label">目标战队</label>
                      <select class="form-select" name="team_id">{transfer_options}</select>
                    </div>
                    <button type="submit" class="btn btn-dark">提交转会申请</button>
                  </form>
                </div>
                """
                if transfer_options and not pending_transfer
                else (
                    f"""
                    <div class="form-panel h-100 p-3 p-lg-4">
                      <h2 class="section-title mb-2">转会申请中</h2>
                      <p class="section-copy mb-4">你已经向目标战队提交了转会申请，等待队长审核。</p>
                      <form method="post" action="/team-center">
                        <input type="hidden" name="action" value="cancel_request">
                        <button type="submit" class="btn btn-outline-dark">取消当前申请</button>
                      </form>
                    </div>
                    """
                    if pending_transfer
                    else """
                    <div class="form-panel h-100 p-3 p-lg-4">
                      <h2 class="section-title mb-2">申请转会</h2>
                      <p class="section-copy mb-0">当前没有其他可转会的战队。</p>
                    </div>
                    """
                )
            )
            leave_panel = (
                '<span class="small text-secondary">转会申请处理中时不可直接退出</span>'
                if pending_transfer
                else (
                    """
                <form method="post" action="/team-center" class="m-0">
                  <input type="hidden" name="action" value="leave_team">
                  <button type="submit" class="btn btn-outline-danger">退出当前战队</button>
                </form>
                """
                    if not user_has_match_history(data, current_player["player_id"])
                    else '<span class="small text-secondary">已有比赛记录时不可直接退出</span>'
                )
            )
            captain_requests = []
            if is_team_captain(current_team, current_player):
                captain_requests = [item for item in requests if item["target_team_id"] == current_team["team_id"]]
            captain_panel = ""
            member_panel = ""
            if is_team_captain(current_team, current_player):
                member_lookup = {player["player_id"]: player for player in data["players"]}
                member_rows = []
                for member_id in current_team["members"]:
                    member = member_lookup.get(member_id)
                    if not member:
                        continue
                    owner_user = get_user_by_player_id(users, member_id)
                    removal_error = get_team_member_removal_error(
                        data, current_team, current_player, member_id
                    )
                    if removal_error:
                        action_html = f'<span class="small text-secondary">{escape(removal_error)}</span>'
                    else:
                        removal_action_html = f"""
                        <form method="post" action="/team-center" class="m-0">
                          <input type="hidden" name="action" value="remove_team_member">
                          <input type="hidden" name="player_id" value="{escape(member_id)}">
                          <button type="submit" class="btn btn-sm btn-outline-danger">删除成员</button>
                        </form>
                        """
                        binding_query = {"player_id": member_id}
                        if owner_user:
                            binding_query["username"] = owner_user["username"]
                        binding_action_html = (
                            f'<a class="btn btn-sm btn-outline-dark" href="/bindings?{urlencode(binding_query)}">帮助绑定数据</a>'
                        )
                        action_html = f'<div class="d-flex flex-wrap gap-2">{binding_action_html}{removal_action_html}</div>'
                    role_badge = (
                        '<span class="chip">队长</span>'
                        if get_team_captain_id(current_team) == member_id
                        else '<span class="chip">正式成员</span>'
                    )
                    member_rows.append(
                        f"""
                        <tr>
                          <td>{escape(member['display_name'])}</td>
                          <td>{escape(member_id)}</td>
                          <td>{escape(owner_user['username']) if owner_user else '未绑定账号'}</td>
                          <td>{role_badge}</td>
                          <td>{escape(member.get('joined_on') or '未知')}</td>
                          <td>{action_html}</td>
                        </tr>
                        """
                    )
                member_panel = f"""
                <section class="panel shadow-sm p-3 p-lg-4 mt-4">
                  <h2 class="section-title mb-2">队长成员管理</h2>
                  <p class="section-copy mb-3">每个战队默认只有一名队长。队长可以审核加入申请，也可以把没有历史比赛记录的成员移出当前战队；这个操作不会删除登录账号。</p>
                  <div class="table-responsive">
                    <table class="table align-middle">
                      <thead>
                        <tr>
                          <th>队员</th>
                          <th>编号</th>
                          <th>绑定账号</th>
                          <th>身份</th>
                          <th>加入日期</th>
                          <th>操作</th>
                        </tr>
                      </thead>
                      <tbody>{''.join(member_rows) or '<tr><td colspan="6" class="text-secondary">当前战队还没有可管理成员。</td></tr>'}</tbody>
                    </table>
                  </div>
                </section>
                """
            if captain_requests:
                request_rows = []
                for item in captain_requests:
                    request_type = "加入申请" if item["request_type"] == "join" else "转会申请"
                    request_rows.append(
                        f"""
                        <tr>
                          <td>{escape(item['display_name'])}</td>
                          <td>{escape(item['username'])}</td>
                          <td>{request_type}</td>
                          <td>{escape(item.get('source_team_id') or '无')}</td>
                          <td>{escape(item['created_on'])}</td>
                          <td>
                            <div class="d-flex flex-wrap gap-2">
                              <form method="post" action="/team-center" class="m-0">
                                <input type="hidden" name="action" value="approve_request">
                                <input type="hidden" name="request_id" value="{escape(item['request_id'])}">
                                <button type="submit" class="btn btn-sm btn-dark">通过</button>
                              </form>
                              <form method="post" action="/team-center" class="m-0">
                                <input type="hidden" name="action" value="reject_request">
                                <input type="hidden" name="request_id" value="{escape(item['request_id'])}">
                                <button type="submit" class="btn btn-sm btn-outline-danger">拒绝</button>
                              </form>
                            </div>
                          </td>
                        </tr>
                        """
                    )
                captain_panel = f"""
                <section class="panel shadow-sm p-3 p-lg-4 mt-4">
                  <h2 class="section-title mb-2">待你审核的申请</h2>
                  <p class="section-copy mb-3">加入申请和转会申请都会在这里处理。</p>
                  <div class="table-responsive">
                    <table class="table align-middle">
                      <thead>
                        <tr>
                          <th>申请人</th>
                          <th>账号</th>
                          <th>类型</th>
                          <th>原战队</th>
                          <th>申请时间</th>
                          <th>操作</th>
                        </tr>
                      </thead>
                      <tbody>{''.join(request_rows)}</tbody>
                    </table>
                  </div>
                </section>
                """
            captain_panel = member_panel + captain_panel
            team_card = f"""
            <section class="hero p-4 p-md-5 shadow-lg mb-4">
              <div class="eyebrow mb-3">当前战队状态</div>
              <h1 class="display-6 fw-semibold mb-3">{escape(current_team['name'])}</h1>
              <p class="mb-2 opacity-75">你当前以队员身份加入该战队，队员名称为 {escape(current_player['display_name'])}。</p>
              <p class="mb-3 opacity-75">当前赛季归属：{escape(team_scope_label(current_team))}</p>
              <div class="d-flex flex-wrap gap-2">
                {captain_badge}
                {current_team_guild_html}
                <a class="btn btn-light" href="/teams/{escape(current_team['team_id'])}">查看战队比赛页</a>
                <a class="btn btn-outline-light" href="/players/{escape(current_player['player_id'])}">查看我的数据</a>
              </div>
            </section>
            {identity_panel}
            <section class="panel shadow-sm p-3 p-lg-4">
              <div class="row g-4">
                <div class="col-12 col-xl-6">
                  {transfer_panel}
                </div>
                <div class="col-12 col-xl-6">
                  <div class="form-panel h-100 p-3 p-lg-4">
                    <h2 class="section-title mb-2">退出当前战队</h2>
                    <p class="section-copy mb-4">{escape(leave_hint)}</p>
                    {leave_panel}
                  </div>
                </div>
              </div>
            </section>
            {captain_panel}
            {season_team_manage_panel}
            """
        else:
            team_card = """
            <div class="alert alert-warning">当前账号已经绑定队员，但没有找到对应战队，请联系管理员排查数据。</div>
            """
        return layout("战队操作", team_card, ctx, alert=alert)

    if current_request:
        request_kind = "加入申请" if current_request["request_type"] == "join" else "转会申请"
        target_team = get_team_by_id(data, current_request["target_team_id"])
        pending_body = f"""
        <section class="hero p-4 p-md-5 shadow-lg mb-4">
          <div class="eyebrow mb-3">申请处理中</div>
          <h1 class="display-6 fw-semibold mb-3">{request_kind}</h1>
          <p class="mb-3 opacity-75">当前申请的目标战队：{escape(target_team['name'] if target_team else current_request['target_team_id'])}</p>
          <div class="d-flex flex-wrap gap-2">
            <form method="post" action="/team-center" class="m-0">
              <input type="hidden" name="action" value="cancel_request">
              <button type="submit" class="btn btn-light">取消当前申请</button>
            </form>
          </div>
        </section>
        """
        return layout("战队操作", pending_body, ctx, alert=alert)

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">战队操作中心</div>
      <h1 class="display-6 fw-semibold mb-3">赛季战队操作中心</h1>
      <p class="mb-0 opacity-75">战队按赛事赛季存在，门派永久存在。你可以在新赛季重新创建战队，或申请加入对应赛季的战队。</p>
    </section>
    {identity_panel}
    {season_team_manage_panel}
    """
    return layout("战队操作", body, ctx, alert=alert)

def handle_team_center(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_team_center_page(ctx))

    current_user = ctx.current_user
    if not current_user:
        return redirect(start_response, "/login?next=/team-center")

    action = form_value(ctx.form, "action")
    data = load_validated_data()
    users = load_users()
    requests = load_membership_requests()
    existing_team_ids = {team["team_id"] for team in data["teams"]}
    existing_player_ids = {player["player_id"] for player in data["players"]}
    username = current_user["username"]
    display_name = current_user.get("display_name") or username
    current_request = next((item for item in requests if item["username"] == username), None)
    current_team = get_team_for_player(data, current_user and get_user_player(data, current_user))
    current_player = get_user_player(data, current_user)
    ongoing_scopes = list_ongoing_team_scopes(data)
    valid_scope_values = {item["value"] for item in ongoing_scopes}

    if action == "switch_primary_identity":
        selected_player_id = form_value(ctx.form, "player_id").strip()
        if not selected_player_id:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="没有找到要切换的赛季身份。"),
            )
        if selected_player_id not in get_user_bound_player_ids(current_user):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">你只能切换到自己已绑定的赛季身份。</div>', ctx),
            )
        users = set_user_primary_player_id(users, username, selected_player_id)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="切换当前管理身份失败：" + "；".join(errors[:3])),
            )
        revoke_user_sessions(username)
        token = secrets.token_urlsafe(24)
        SESSIONS[token] = username
        return redirect(
            start_response,
            "/team-center",
            headers=[("Set-Cookie", f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax")],
        )

    if action == "create_team":
        if current_request:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="你当前有待处理申请，请先取消或等待审核。"),
            )
        selected_scope = form_value(ctx.form, "team_scope").strip()
        competition_name, season_name = parse_team_scope_value(selected_scope)
        team_name = form_value(ctx.form, "team_name").strip()
        short_name = form_value(ctx.form, "short_name").strip()
        notes = form_value(ctx.form, "notes").strip()
        if selected_scope not in valid_scope_values:
            error = "请从正在进行中的赛季列表里选择要创建战队的赛事。"
        elif user_has_team_identity_in_scope(data, current_user, competition_name, season_name):
            error = "当前账号在这个赛事赛季里已经绑定了队员身份，不能重复创建战队。"
        else:
            error = validate_team_creation(
                team_name,
                short_name,
                competition_name,
                season_name,
                data["teams"],
            )
        if error:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(
                    ctx,
                    alert=error,
                    create_values={
                        "scope": selected_scope,
                        "name": team_name,
                        "short_name": short_name,
                        "notes": notes,
                    },
                ),
            )

        player_id = build_unique_slug(existing_player_ids, "player", username, "player")
        team_id = build_team_serial(data, competition_name, season_name, data["teams"])
        data["players"].append(
            {
                "player_id": player_id,
                "display_name": display_name,
                "team_id": team_id,
                "photo": DEFAULT_PLAYER_PHOTO,
                "aliases": [],
                "active": True,
                "joined_on": china_today_label(),
                "notes": "网站账号创建战队时自动生成的队员档案。",
            }
        )
        data["teams"].append(
            {
                "team_id": team_id,
                "name": team_name,
                "short_name": short_name,
                "logo": DEFAULT_TEAM_LOGO,
                "active": True,
                "founded_on": china_today_label(),
                "competition_name": competition_name,
                "season_name": season_name,
                "guild_id": "",
                "captain_player_id": player_id,
                "members": [player_id],
                "notes": notes or f"由网站账号创建，用于 {competition_name} / {season_name}。",
            }
        )
        users = append_user_player_binding(users, username, player_id)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(
                    ctx,
                    alert="创建战队失败：" + "；".join(errors[:3]),
                    create_values={
                        "scope": selected_scope,
                        "name": team_name,
                        "short_name": short_name,
                        "notes": notes,
                    },
                ),
            )
        return redirect(
            start_response,
            build_scoped_path(f"/teams/{team_id}", competition_name, season_name),
        )

    if action == "request_join":
        if current_request:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="你当前已经有待处理申请。"),
            )
        team_id = form_value(ctx.form, "team_id").strip()
        target_team = next((team for team in data["teams"] if team["team_id"] == team_id), None)
        if not target_team:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="没有找到要加入的战队。"),
            )
        competition_name, season_name = get_team_scope(target_team)
        if user_has_team_identity_in_scope(data, current_user, competition_name, season_name):
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(
                    ctx,
                    alert="当前账号在这个赛事赛季里已经有战队身份，如需切换请使用转会申请。",
                    join_values={"team_id": team_id},
                ),
            )
        requests.append(
            {
                "request_id": secrets.token_urlsafe(12),
                "request_type": "join",
                "username": username,
                "display_name": display_name,
                "player_id": None,
                "source_team_id": None,
                "target_team_id": team_id,
                "target_guild_id": "",
                "scope_competition_name": competition_name,
                "scope_season_name": season_name,
                "created_on": china_now_label(),
            }
        )
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_team_center_page(ctx, alert="加入申请已提交，等待队长审核。"),
        )

    if action == "request_transfer":
        if not current_player or not current_team:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="当前账号还没有战队身份，无法发起转会。"),
            )
        if current_request:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="你当前已经有待处理申请。"),
            )
        team_id = form_value(ctx.form, "team_id").strip()
        if team_id == current_team["team_id"]:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="不能把自己转会到当前战队。"),
            )
        target_team = next((team for team in data["teams"] if team["team_id"] == team_id), None)
        if not target_team:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="没有找到目标战队。"),
            )
        if get_team_scope(target_team) != get_team_scope(current_team):
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="转会只能发生在同一赛事赛季内的战队之间。"),
            )
        requests.append(
            {
                "request_id": secrets.token_urlsafe(12),
                "request_type": "transfer",
                "username": username,
                "display_name": display_name,
                "player_id": current_player["player_id"],
                "source_team_id": current_team["team_id"],
                "target_team_id": team_id,
                "target_guild_id": "",
                "scope_competition_name": current_team.get("competition_name", ""),
                "scope_season_name": current_team.get("season_name", ""),
                "created_on": china_now_label(),
            }
        )
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_team_center_page(ctx, alert="转会申请已提交，等待目标战队队长审核。"),
        )

    if action == "cancel_request":
        if not current_request:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="当前没有可取消的申请。"),
            )
        requests = [item for item in requests if item["username"] != username]
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_team_center_page(ctx, alert="申请已取消。"),
        )

    if action == "leave_team":
        if not current_player or not current_team:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="当前账号没有可退出的战队。"),
            )
        if current_request:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="你当前有待处理申请，请先取消申请或等待审核后再退出战队。"),
            )
        if user_has_match_history(data, current_player["player_id"]):
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="已有比赛记录时不能直接退出战队，请改用转会申请。"),
            )
        remove_member_from_team(current_team, current_player["player_id"])
        data["players"] = [item for item in data["players"] if item["player_id"] != current_player["player_id"]]
        users = append_user_player_binding(users, username, None)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="退出战队失败：" + "；".join(errors[:3])),
            )
        revoke_user_sessions(username)
        token = secrets.token_urlsafe(24)
        SESSIONS[token] = username
        return redirect(
            start_response,
            "/team-center",
            headers=[("Set-Cookie", f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax")],
        )

    if action == "remove_team_member":
        can_manage_current_team = bool(
            current_team
            and (
                user_has_permission(current_user, "team_manage")
                or (current_player and is_team_captain(current_team, current_player))
            )
        )
        if not can_manage_current_team or not current_player or not current_team:
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">只有当前战队队长或具备战队管理权限的账号可以删除成员。</div>', ctx),
            )
        member_player_id = form_value(ctx.form, "player_id").strip()
        removal_error = get_team_member_removal_error(
            data, current_team, current_player, member_player_id
        )
        if removal_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert=removal_error),
            )
        member = next(
            (item for item in data["players"] if item["player_id"] == member_player_id),
            None,
        )
        if not member:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="没有找到要删除的队员。"),
            )
        owner_user = get_user_by_player_id(users, member_player_id)
        owner_username = owner_user["username"] if owner_user else ""
        remove_member_from_team(current_team, member_player_id)
        data["players"] = [
            item for item in data["players"] if item["player_id"] != member_player_id
        ]
        if owner_username:
            users = append_user_player_binding(users, owner_username, None)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="删除成员失败：" + "；".join(errors[:3])),
            )
        requests = [
            item
            for item in requests
            if item.get("player_id") != member_player_id
            and (not owner_username or item["username"] != owner_username)
        ]
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_team_center_page(ctx, alert=f"队员 {member['display_name']} 已从战队移除。"),
        )

    if action in {"approve_request", "reject_request"}:
        can_manage_current_team = bool(
            current_team
            and (
                user_has_permission(current_user, "team_manage")
                or (current_player and is_team_captain(current_team, current_player))
            )
        )
        if not can_manage_current_team or not current_player or not current_team:
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">只有当前战队队长或具备战队管理权限的账号可以审核申请。</div>', ctx),
            )
        request_id = form_value(ctx.form, "request_id").strip()
        request_item = next(
            (item for item in requests if item["request_id"] == request_id and item["target_team_id"] == current_team["team_id"]),
            None,
        )
        if not request_item:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="没有找到对应申请。"),
            )
        if action == "reject_request":
            requests = [item for item in requests if item["request_id"] != request_id]
            save_membership_requests(requests)
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="申请已拒绝。"),
            )

        requester = next((user for user in users if user["username"] == request_item["username"]), None)
        if not requester:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="申请账号不存在，无法审核。"),
            )
        if request_item["request_type"] == "join":
            request_competition_name = str(request_item.get("scope_competition_name") or "").strip()
            request_season_name = str(request_item.get("scope_season_name") or "").strip()
            if user_has_team_identity_in_scope(
                data,
                requester,
                request_competition_name,
                request_season_name,
            ):
                requests = [item for item in requests if item["request_id"] != request_id]
                save_membership_requests(requests)
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_team_center_page(ctx, alert="该账号在当前赛事赛季里已经加入其他战队，申请已移除。"),
                )
            player_id = build_unique_slug(existing_player_ids, "player", requester["username"], "player")
            current_team["members"].append(player_id)
            if not current_team.get("captain_player_id"):
                current_team["captain_player_id"] = current_player["player_id"]
            data["players"].append(
                {
                    "player_id": player_id,
                    "display_name": requester.get("display_name") or requester["username"],
                    "team_id": current_team["team_id"],
                    "photo": DEFAULT_PLAYER_PHOTO,
                    "aliases": [],
                    "active": True,
                    "joined_on": china_today_label(),
                    "notes": f"经战队队长审核通过后加入战队：{team_scope_label(current_team)}。",
                }
            )
            users = append_user_player_binding(users, requester["username"], player_id)
        else:
            transfer_player = next((item for item in data["players"] if item["player_id"] == request_item["player_id"]), None)
            source_team = get_team_by_id(data, request_item["source_team_id"] or "")
            if not transfer_player or not source_team:
                requests = [item for item in requests if item["request_id"] != request_id]
                save_membership_requests(requests)
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_team_center_page(ctx, alert="转会申请对应的数据已失效，申请已移除。"),
                )
            remove_member_from_team(source_team, transfer_player["player_id"])
            current_team["members"].append(transfer_player["player_id"])
            transfer_player["team_id"] = current_team["team_id"]
            if not current_team.get("captain_player_id"):
                current_team["captain_player_id"] = current_player["player_id"]

        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="审核失败：" + "；".join(errors[:3])),
            )
        requests = [item for item in requests if item["request_id"] != request_id]
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_team_center_page(ctx, alert="申请已通过。"),
        )

    return start_response_html(start_response, "200 OK", get_team_center_page(ctx, alert="未识别的操作。"))
