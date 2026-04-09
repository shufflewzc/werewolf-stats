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
can_manage_matches = legacy.can_manage_matches
china_now_label = legacy.china_now_label
china_today_label = legacy.china_today_label
find_team_by_name_in_scope = legacy.find_team_by_name_in_scope
find_player_by_name_in_scope = legacy.find_player_by_name_in_scope
form_value = legacy.form_value
get_guild_by_id = legacy.get_guild_by_id
get_team_by_id = legacy.get_team_by_id
get_team_captain_id = legacy.get_team_captain_id
get_team_for_player = legacy.get_team_for_player
get_team_scope = legacy.get_team_scope
get_team_season_status = legacy.get_team_season_status
get_user_bound_player_ids = legacy.get_user_bound_player_ids
get_user_badge_label = legacy.get_user_badge_label
get_user_by_player_id = legacy.get_user_by_player_id
get_user_player = legacy.get_user_player
get_user_team_identities = legacy.get_user_team_identities
is_admin_user = legacy.is_admin_user
is_placeholder_team = legacy.is_placeholder_team
is_placeholder_user = legacy.is_placeholder_user
is_team_captain = legacy.is_team_captain
layout = legacy.layout
list_team_scopes = legacy.list_team_scopes
list_ongoing_team_scopes = legacy.list_ongoing_team_scopes
load_membership_requests = legacy.load_membership_requests
load_users = legacy.load_users
load_validated_data = legacy.load_validated_data
parse_team_scope_value = legacy.parse_team_scope_value
redirect = legacy.redirect
remove_member_from_team = legacy.remove_member_from_team
remove_user_player_binding = legacy.remove_user_player_binding
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
build_placeholder_player = legacy.build_placeholder_player


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


def get_team_membership_change_error(
    data: dict[str, Any],
    team: dict[str, Any] | None,
    action_label: str,
) -> str:
    if not team:
        return f"没有找到要{action_label}的战队。"
    if get_team_season_status(data, team) != "ongoing":
        return f"当前战队所属赛季已结束，不能再{action_label}。"
    return ""


def get_team_dissolution_error(
    data: dict[str, Any],
    team: dict[str, Any] | None,
    action_label: str = "解散战队",
) -> str:
    if not team:
        return f"当前战队不存在，无法{action_label}。"
    for member_id in team.get("members", []):
        if user_has_match_history(data, member_id):
            return f"当前战队已有成员产生历史比赛记录，不能直接{action_label}，请联系管理员处理历史数据。"
    return ""


def dissolve_team(
    data: dict[str, Any],
    users: list[dict[str, Any]],
    team: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    removed_member_ids = set(team.get("members", []))
    data["players"] = [
        item for item in data["players"] if item["player_id"] not in removed_member_ids
    ]
    data["teams"] = [
        item for item in data["teams"] if item["team_id"] != team["team_id"]
    ]
    for member_id in removed_member_ids:
        owner_user = get_user_by_player_id(users, member_id)
        if owner_user:
            users = remove_user_player_binding(users, owner_user["username"], member_id)
    requests = [
        item
        for item in load_membership_requests()
        if item.get("target_team_id") != team["team_id"]
        and item.get("source_team_id") != team["team_id"]
    ]
    return users, requests


def issue_fresh_team_center_session(
    start_response,
    username: str,
):
    revoke_user_sessions(username)
    token = secrets.token_urlsafe(24)
    SESSIONS[token] = username
    return redirect(
        start_response,
        "/team-center",
        headers=[("Set-Cookie", f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax")],
    )


def can_manage_current_team_members(
    current_user: dict[str, Any] | None,
    current_player: dict[str, Any] | None,
    current_team: dict[str, Any] | None,
) -> bool:
    return bool(
        current_team
        and (
            user_has_permission(current_user, "team_manage")
            or (current_player and is_team_captain(current_team, current_player))
        )
    )


def can_seed_team_for_scope(current_user: dict[str, Any] | None) -> bool:
    return bool(
        current_user
        and (
            is_admin_user(current_user)
            or user_has_permission(current_user, "team_manage")
        )
    )


def can_review_team_claim_request(
    data: dict[str, Any],
    acting_user: dict[str, Any] | None,
    target_team: dict[str, Any] | None,
) -> bool:
    if not acting_user or not target_team:
        return False
    if is_admin_user(acting_user) or user_has_permission(acting_user, "team_manage"):
        return True
    competition_name, _ = get_team_scope(target_team)
    return bool(competition_name and can_manage_matches(acting_user, data, competition_name))


def remove_placeholder_owner(users: list[dict[str, Any]], player_id: str) -> list[dict[str, Any]]:
    owner_user = get_user_by_player_id(users, player_id)
    if not owner_user or not is_placeholder_user(owner_user):
        return users
    return [user for user in users if user["username"] != owner_user["username"]]


def handle_switch_primary_identity_action(
    ctx: RequestContext,
    start_response,
    data: dict[str, Any],
    users: list[dict[str, Any]],
    current_user: dict[str, Any],
):
    username = current_user["username"]
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
    return issue_fresh_team_center_session(start_response, username)


def handle_cancel_request_action(
    ctx: RequestContext,
    start_response,
    current_request: dict[str, Any] | None,
    requests: list[dict[str, Any]],
    username: str,
):
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


def handle_leave_team_action(
    ctx: RequestContext,
    start_response,
    data: dict[str, Any],
    users: list[dict[str, Any]],
    current_request: dict[str, Any] | None,
    current_player: dict[str, Any] | None,
    current_team: dict[str, Any] | None,
    username: str,
):
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
    if is_team_captain(current_team, current_player):
        dissolution_error = get_team_dissolution_error(data, current_team, "解散战队")
        if dissolution_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert=dissolution_error),
            )
        users, requests = dissolve_team(data, users, current_team)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="解散战队失败：" + "；".join(errors[:3])),
            )
        save_membership_requests(requests)
        return issue_fresh_team_center_session(start_response, username)
    remove_member_from_team(current_team, current_player["player_id"])
    data["players"] = [item for item in data["players"] if item["player_id"] != current_player["player_id"]]
    users = remove_user_player_binding(users, username, current_player["player_id"])
    errors = save_repository_state(data, users)
    if errors:
        return start_response_html(
            start_response,
            "200 OK",
            get_team_center_page(ctx, alert="退出战队失败：" + "；".join(errors[:3])),
        )
    return issue_fresh_team_center_session(start_response, username)

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
            and item["request_type"] in {"join", "transfer", "team_claim"}
        ),
        None,
    )
    createable_scopes = list_team_scopes(data, {"ongoing", "upcoming"})
    ongoing_scopes = list_ongoing_team_scopes(data)
    user_scope_keys = {
        build_team_scope_value(*get_team_scope(team))
        for _, team in get_user_team_identities(data, current_user)
    }
    create_scope_options = "".join(
        f'<option value="{escape(scope["value"])}"{" selected" if create_form["scope"] == scope["value"] else ""}>{escape(scope["label"])}</option>'
        for scope in createable_scopes
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
                else '<div class="small text-secondary">当前没有可创建战队的赛季。请先让赛事负责人配置赛季档期，并确认赛季状态为未开始或进行中。</div>'
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
    team_claim_rows = []
    if current_user:
        for item in requests:
            if item.get("request_type") != "team_claim":
                continue
            target_team = get_team_by_id(data, item.get("target_team_id", ""))
            if not can_review_team_claim_request(data, current_user, target_team):
                continue
            payload = item.get("request_payload", {})
            team_claim_rows.append(
                f"""
                <tr>
                  <td>{escape(item['display_name'])}</td>
                  <td>{escape(item['username'])}</td>
                  <td>{escape(target_team['name'] if target_team else item.get('target_team_id', ''))}</td>
                  <td>{escape(team_scope_label(target_team) if target_team else ((item.get('scope_competition_name') or '') + ' / ' + (item.get('scope_season_name') or '')))}</td>
                  <td>{escape(payload.get('short_name', ''))}</td>
                  <td>{escape(item.get('created_on') or '')}</td>
                  <td>
                    <div class="d-flex flex-wrap gap-2">
                      <form method="post" action="/team-center" class="m-0">
                        <input type="hidden" name="action" value="approve_team_claim">
                        <input type="hidden" name="request_id" value="{escape(item['request_id'])}">
                        <button type="submit" class="btn btn-sm btn-dark">通过</button>
                      </form>
                      <form method="post" action="/team-center" class="m-0">
                        <input type="hidden" name="action" value="reject_team_claim">
                        <input type="hidden" name="request_id" value="{escape(item['request_id'])}">
                        <button type="submit" class="btn btn-sm btn-outline-danger">拒绝</button>
                      </form>
                    </div>
                  </td>
                </tr>
                """
            )
    team_claim_panel = ""
    if team_claim_rows:
        team_claim_panel = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mt-4">
          <h2 class="section-title mb-2">待审核的战队认领申请</h2>
          <p class="section-copy mb-3">当比赛先录入、战队后补建时，可以在这里把占位战队认领为正式战队。</p>
          <div class="table-responsive">
            <table class="table align-middle">
              <thead>
                <tr>
                  <th>申请人</th>
                  <th>账号</th>
                  <th>目标战队</th>
                  <th>赛事赛季</th>
                  <th>简称</th>
                  <th>申请时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>{''.join(team_claim_rows)}</tbody>
            </table>
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
                and not is_placeholder_team(team)
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
                          <td>{escape(get_user_badge_label(owner_user))}</td>
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
            {team_claim_panel}
            """
        else:
            team_card = """
            <div class="alert alert-warning">当前账号已经绑定队员，但没有找到对应战队，请联系管理员排查数据。</div>
            """
        return layout("战队操作", team_card, ctx, alert=alert)

    if current_request:
        request_kind = {
            "join": "加入申请",
            "transfer": "转会申请",
            "team_claim": "战队认领申请",
        }.get(current_request["request_type"], "申请")
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
    {team_claim_panel}
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
    creatable_scopes = list_team_scopes(data, {"ongoing", "upcoming"})
    valid_scope_values = {item["value"] for item in creatable_scopes}

    if action == "switch_primary_identity":
        return handle_switch_primary_identity_action(
            ctx,
            start_response,
            data,
            users,
            current_user,
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
        normalized_scope_value = build_team_scope_value(competition_name, season_name)
        team_name = form_value(ctx.form, "team_name").strip()
        short_name = form_value(ctx.form, "short_name").strip()
        notes = form_value(ctx.form, "notes").strip()
        can_seed_without_binding = can_seed_team_for_scope(current_user)
        placeholder_team = find_team_by_name_in_scope(data, competition_name, season_name, team_name)
        if normalized_scope_value not in valid_scope_values:
            error = "请从可创建的赛季列表里选择要创建战队的赛事。"
        elif (
            user_has_team_identity_in_scope(data, current_user, competition_name, season_name)
            and not can_seed_without_binding
        ):
            error = "当前账号在这个赛事赛季里已经绑定了队员身份，不能重复创建战队。"
        elif placeholder_team and is_placeholder_team(placeholder_team):
            error = validate_team_creation(
                team_name,
                short_name,
                competition_name,
                season_name,
                [team for team in data["teams"] if team["team_id"] != placeholder_team["team_id"]],
            )
            if error:
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_team_center_page(
                        ctx,
                        alert=error,
                        create_values={
                            "scope": normalized_scope_value,
                            "name": team_name,
                            "short_name": short_name,
                            "notes": notes,
                        },
                    ),
                )
            requests.append(
                {
                    "request_id": secrets.token_urlsafe(12),
                    "request_type": "team_claim",
                    "username": username,
                    "display_name": display_name,
                    "player_id": None,
                    "source_team_id": None,
                    "target_team_id": placeholder_team["team_id"],
                    "target_guild_id": "",
                    "scope_competition_name": competition_name,
                    "scope_season_name": season_name,
                    "request_payload": {
                        "team_name": team_name,
                        "short_name": short_name,
                        "notes": notes,
                    },
                    "created_on": china_now_label(),
                }
            )
            save_membership_requests(requests)
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="同一赛季内不允许重名战队。当前赛季已存在同名占位战队，已转为认领申请，请等待管理员或赛事管理员审批。"),
            )
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
                        "scope": normalized_scope_value,
                        "name": team_name,
                        "short_name": short_name,
                        "notes": notes,
                    },
                ),
            )

        team_id = build_team_serial(data, competition_name, season_name, data["teams"])
        should_create_bound_captain = not user_has_team_identity_in_scope(
            data,
            current_user,
            competition_name,
            season_name,
        )
        player_id: str | None = None
        team_alert = ""
        if should_create_bound_captain:
            player_id = build_unique_slug(existing_player_ids, "player", username, "player")
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
        else:
            team_alert = "当前账号在该赛季已有身份，已改为创建待认领战队，不会重复绑定到你的账号。后续可由赛事管理员或队长认领并补充资料。"
        data["teams"].append(
            {
                "team_id": team_id,
                "name": team_name,
                "short_name": short_name,
                "logo": DEFAULT_TEAM_LOGO,
                "active": True,
                "is_placeholder_team": not should_create_bound_captain,
                "placeholder_source_name": team_name if not should_create_bound_captain else None,
                "founded_on": china_today_label(),
                "competition_name": competition_name,
                "season_name": season_name,
                "guild_id": "",
                "captain_player_id": player_id,
                "members": [player_id] if player_id else [],
                "notes": notes
                or (
                    f"由网站账号创建，用于 {competition_name} / {season_name}。"
                    if should_create_bound_captain
                    else f"由管理员预创建，等待 {competition_name} / {season_name} 赛季战队负责人认领。"
                ),
            }
        )
        if player_id:
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
                        "scope": normalized_scope_value,
                        "name": team_name,
                        "short_name": short_name,
                        "notes": notes,
                    },
                ),
            )
        team_path = build_scoped_path(f"/teams/{team_id}", competition_name, season_name)
        if team_alert:
            team_path = f"{team_path}{'&' if '?' in team_path else '?'}notice=seeded"
        return redirect(start_response, team_path)

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
        if is_placeholder_team(target_team):
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="目标战队还是未认领的占位战队，暂时不能发起转会，请等待战队负责人先完成认领。"),
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

    if action in {"approve_team_claim", "reject_team_claim"}:
        request_id = form_value(ctx.form, "request_id").strip()
        request_item = next(
            (item for item in requests if item.get("request_id") == request_id and item.get("request_type") == "team_claim"),
            None,
        )
        if not request_item:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="没有找到对应的战队认领申请。"),
            )
        target_team = get_team_by_id(data, request_item.get("target_team_id") or "")
        if not can_review_team_claim_request(data, current_user, target_team):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">你没有权限审核这条战队认领申请。</div>', ctx),
            )
        if action == "reject_team_claim":
            requests = [item for item in requests if item.get("request_id") != request_id]
            save_membership_requests(requests)
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="战队认领申请已拒绝。"),
            )
        requester = next((user for user in users if user["username"] == request_item["username"]), None)
        if not requester or not target_team or not is_placeholder_team(target_team):
            requests = [item for item in requests if item.get("request_id") != request_id]
            save_membership_requests(requests)
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="战队认领申请对应的数据已失效，申请已移除。"),
            )
        competition_name, season_name = get_team_scope(target_team)
        if user_has_team_identity_in_scope(data, requester, competition_name, season_name):
            requests = [item for item in requests if item.get("request_id") != request_id]
            save_membership_requests(requests)
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="该账号在当前赛事赛季里已经有战队身份，申请已移除。"),
            )
        payload = request_item.get("request_payload", {})
        captain_player = find_player_by_name_in_scope(
            data,
            competition_name,
            season_name,
            requester.get("display_name") or requester["username"],
        )
        if captain_player and captain_player["team_id"] != target_team["team_id"]:
            captain_player = None
        if captain_player is None:
            player_id = build_unique_slug(existing_player_ids, "player", requester["username"], "player")
            captain_player = build_placeholder_player(
                player_id,
                target_team["team_id"],
                competition_name,
                season_name,
                display_name=requester.get("display_name") or requester["username"],
            )
            captain_player["notes"] = "经管理员审核通过后认领占位战队时创建的队长档案。"
            data["players"].append(captain_player)
            if player_id not in target_team["members"]:
                target_team["members"].append(player_id)
        users = remove_placeholder_owner(users, captain_player["player_id"])
        users = append_user_player_binding(users, requester["username"], captain_player["player_id"])
        target_team["name"] = str(payload.get("team_name") or target_team["name"]).strip() or target_team["name"]
        target_team["short_name"] = str(payload.get("short_name") or target_team["short_name"]).strip() or target_team["short_name"]
        target_team["notes"] = str(payload.get("notes") or target_team["notes"]).strip() or target_team["notes"]
        target_team["active"] = True
        target_team["is_placeholder_team"] = False
        target_team["placeholder_source_name"] = None
        target_team["captain_player_id"] = captain_player["player_id"]
        if captain_player["player_id"] not in target_team["members"]:
            target_team["members"].insert(0, captain_player["player_id"])
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="通过认领申请失败：" + "；".join(errors[:3])),
            )
        requests = [item for item in requests if item.get("request_id") != request_id]
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_team_center_page(ctx, alert=f"已通过 {target_team['name']} 的战队认领申请。"),
        )

    if action == "cancel_request":
        return handle_cancel_request_action(
            ctx,
            start_response,
            current_request,
            requests,
            username,
        )

    if action == "leave_team":
        return handle_leave_team_action(
            ctx,
            start_response,
            data,
            users,
            current_request,
            current_player,
            current_team,
            username,
        )

    if action == "remove_team_member":
        can_manage_current_team = can_manage_current_team_members(
            current_user,
            current_player,
            current_team,
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
            users = remove_user_player_binding(users, owner_username, member_player_id)
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

    if action == "delete_team":
        if not is_admin_user(current_user):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">只有管理员可以删除战队。</div>', ctx),
            )
        team_id = form_value(ctx.form, "team_id").strip()
        team = get_team_by_id(data, team_id)
        if not team:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="没有找到要删除的战队。"),
            )
        dissolution_error = get_team_dissolution_error(data, team, "删除战队")
        if dissolution_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert=dissolution_error),
            )
        users, requests = dissolve_team(data, users, team)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="删除战队失败：" + "；".join(errors[:3])),
            )
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_team_center_page(ctx, alert=f"战队 {team['name']} 已删除。"),
        )

    if action in {"approve_request", "reject_request"}:
        can_manage_current_team = can_manage_current_team_members(
            current_user,
            current_player,
            current_team,
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
        membership_error = get_team_membership_change_error(data, current_team, "审核成员申请")
        if membership_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert=membership_error),
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
            if (request_competition_name, request_season_name) != get_team_scope(current_team):
                requests = [item for item in requests if item["request_id"] != request_id]
                save_membership_requests(requests)
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_team_center_page(ctx, alert="该申请所属赛事赛季与当前战队不一致，申请已移除。"),
                )
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
            existing_player = find_player_by_name_in_scope(
                data,
                request_competition_name,
                request_season_name,
                requester.get("display_name") or requester["username"],
            )
            if existing_player and existing_player["team_id"] != current_team["team_id"]:
                requests = [item for item in requests if item["request_id"] != request_id]
                save_membership_requests(requests)
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_team_center_page(
                        ctx,
                        alert=f"同一赛季内不允许重名选手。{existing_player['display_name']} 已存在于本赛季其他战队，申请已移除。",
                    ),
                )
            if existing_player:
                player_id = existing_player["player_id"]
                existing_player["team_id"] = current_team["team_id"]
                existing_player["active"] = True
            else:
                player_id = build_unique_slug(existing_player_ids, "player", requester["username"], "player")
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
            if player_id not in current_team["members"]:
                current_team["members"].append(player_id)
            if not current_team.get("captain_player_id"):
                current_team["captain_player_id"] = current_player["player_id"]
            users = remove_placeholder_owner(users, player_id)
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
            if get_team_scope(source_team) != get_team_scope(current_team):
                requests = [item for item in requests if item["request_id"] != request_id]
                save_membership_requests(requests)
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_team_center_page(ctx, alert="转会申请对应的战队赛季范围已变化，申请已移除。"),
                )
            if transfer_player["team_id"] != source_team["team_id"]:
                requests = [item for item in requests if item["request_id"] != request_id]
                save_membership_requests(requests)
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_team_center_page(ctx, alert="转会申请对应的队员已不在原战队中，申请已移除。"),
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
