from __future__ import annotations

from html import escape
import secrets

import web_app as legacy
from web.features import team_center as base

RequestContext = legacy.RequestContext
append_alert_query = legacy.append_alert_query
append_user_player_binding = legacy.append_user_player_binding
build_placeholder_player = legacy.build_placeholder_player
build_scoped_path = legacy.build_scoped_path
build_unique_slug = legacy.build_unique_slug
can_manage_team = legacy.can_manage_team
find_player_by_name_in_scope = legacy.find_player_by_name_in_scope
form_value = legacy.form_value
get_guild_by_id = legacy.get_guild_by_id
get_team_by_id = legacy.get_team_by_id
get_team_captain_id = legacy.get_team_captain_id
get_team_scope = legacy.get_team_scope
get_team_season_status = legacy.get_team_season_status
get_user_player = legacy.get_user_player
get_user_team_identities = legacy.get_user_team_identities
is_admin_user = legacy.is_admin_user
layout = legacy.layout
load_membership_requests = legacy.load_membership_requests
load_users = legacy.load_users
load_validated_data = legacy.load_validated_data
redirect = legacy.redirect
save_membership_requests = legacy.save_membership_requests
save_repository_state = legacy.save_repository_state
start_response_html = legacy.start_response_html
team_scope_label = legacy.team_scope_label
user_has_team_identity_in_scope = legacy.user_has_team_identity_in_scope

collect_team_stage_groups_from_form = base.collect_team_stage_groups_from_form
handle_switch_primary_identity_action = base.handle_switch_primary_identity_action
issue_fresh_team_center_session = base.issue_fresh_team_center_session
can_review_team_claim_request = base.can_review_team_claim_request
is_unclaimed_team = base.is_unclaimed_team
get_team_dissolution_error = base.get_team_dissolution_error
dissolve_team = base.dissolve_team


def _status_label(status: str) -> str:
    return {
        "ongoing": "进行中",
        "upcoming": "未开始",
        "completed": "已结束",
        "unknown": "未配置",
    }.get(status, "未配置")


def _status_rank(status: str) -> int:
    return {"ongoing": 0, "upcoming": 1, "completed": 2, "unknown": 3}.get(status, 3)


def _respond_with_alert(start_response, ctx: RequestContext, alert: str, next_path: str = ""):
    if next_path:
        return redirect(start_response, append_alert_query(next_path, alert))
    return start_response_html(start_response, "200 OK", get_team_center_page_impl(ctx, alert))


def get_team_center_page_impl(
    ctx: RequestContext,
    alert: str = "",
    join_values: dict[str, str] | None = None,
) -> str:
    del join_values
    if not ctx.current_user:
        return layout(
            "战队认领",
            '<div class="alert alert-danger">请先登录后再认领战队或切换赛季身份。</div>',
            ctx,
            alert=alert,
        )

    data = load_validated_data()
    requests = load_membership_requests()
    current_user = ctx.current_user
    current_player = get_user_player(data, current_user)
    current_request = next(
        (
            item
            for item in requests
            if item.get("username") == current_user["username"]
            and item.get("request_type") == "team_claim"
        ),
        None,
    )

    identity_cards: list[str] = []
    for player, team in sorted(
        get_user_team_identities(data, current_user),
        key=lambda pair: (
            _status_rank(get_team_season_status(data, pair[1])),
            pair[1].get("competition_name", ""),
            pair[1].get("season_name", ""),
            pair[1].get("name", ""),
        ),
    ):
        team_status = get_team_season_status(data, team)
        guild = get_guild_by_id(data, str(team.get("guild_id") or "").strip())
        scope = get_team_scope(team)
        switch_action = (
            '<span class="chip">当前主身份</span>'
            if current_player and current_player["player_id"] == player["player_id"]
            else f"""
            <form method="post" action="/team-center" class="m-0">
              <input type="hidden" name="action" value="switch_primary_identity">
              <input type="hidden" name="player_id" value="{escape(player['player_id'])}">
              <button type="submit" class="btn btn-sm btn-outline-dark">切换为主身份</button>
            </form>
            """
        )
        identity_cards.append(
            f"""
            <div class="col-12 col-xl-6">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div class="card-kicker mb-2">{escape(_status_label(team_status))}</div>
                    <h3 class="h5 mb-1">{escape(team['name'])}</h3>
                    <div class="small-muted">{escape(team_scope_label(team))}</div>
                  </div>
                  <span class="chip">{'认领负责人' if get_team_captain_id(team) == player['player_id'] else '已绑定身份'}</span>
                </div>
                <div class="small text-secondary mt-3">赛季参赛 ID：{escape(player['player_id'])}</div>
                <div class="d-flex flex-wrap gap-2 mt-2">
                  {f'<a class="chip" href="/guilds/{escape(guild["guild_id"])}">{escape(guild["name"])}</a>' if guild else '<span class="chip">未加入门派</span>'}
                </div>
                <div class="d-flex flex-wrap gap-2 mt-3">
                  <a class="btn btn-sm btn-dark" href="{escape(build_scoped_path('/teams/' + team['team_id'], *scope))}">查看战队页</a>
                  <a class="btn btn-sm btn-outline-dark" href="{escape(build_scoped_path('/players/' + player['player_id'], *scope))}">查看档案</a>
                  {switch_action}
                </div>
              </div>
            </div>
            """
        )

    claim_cards: list[str] = []
    for team in sorted(
        data["teams"],
        key=lambda item: (
            _status_rank(get_team_season_status(data, item)),
            item.get("competition_name", ""),
            item.get("season_name", ""),
            item.get("name", ""),
        ),
    ):
        team_status = get_team_season_status(data, team)
        if team_status == "completed" or not is_unclaimed_team(team):
            continue
        competition_name, season_name = get_team_scope(team)
        if user_has_team_identity_in_scope(data, current_user, competition_name, season_name):
            continue
        guild = get_guild_by_id(data, str(team.get("guild_id") or "").strip())
        claim_cards.append(
            f"""
            <div class="col-12 col-xl-6">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div class="card-kicker mb-2">待认领 · {escape(_status_label(team_status))}</div>
                    <h3 class="h5 mb-1">{escape(team['name'])}</h3>
                    <div class="small-muted">{escape(team_scope_label(team))}</div>
                  </div>
                  <span class="chip">{escape(guild['name']) if guild else '独立战队'}</span>
                </div>
                <div class="small text-secondary mt-3">{escape(team.get('notes') or '战队简介待完善。')}</div>
                <div class="d-flex flex-wrap gap-2 mt-3">
                  <a class="btn btn-sm btn-outline-dark" href="{escape(build_scoped_path('/teams/' + team['team_id'], competition_name, season_name))}">查看巡礼页</a>
                  <form method="post" action="/team-center" class="m-0">
                    <input type="hidden" name="action" value="request_team_claim">
                    <input type="hidden" name="team_id" value="{escape(team['team_id'])}">
                    <button type="submit" class="btn btn-sm btn-dark"{' disabled' if current_request else ''}>申请认领</button>
                  </form>
                </div>
              </div>
            </div>
            """
        )

    pending_panel = ""
    if current_request:
        target_team = get_team_by_id(data, str(current_request.get("target_team_id") or "").strip())
        pending_panel = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <h2 class="section-title mb-2">当前申请</h2>
          <p class="section-copy mb-3">你已经提交了一条战队认领申请，新的认领申请会先被锁住，直到这条申请处理完成。</p>
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-center gap-3">
            <div>
              <div class="fw-semibold">{escape(target_team['name'] if target_team else current_request.get('target_team_id', '未知战队'))}</div>
              <div class="small text-secondary">{escape(team_scope_label(target_team) if target_team else ((current_request.get('scope_competition_name') or '') + ' / ' + (current_request.get('scope_season_name') or '')))}</div>
              <div class="small text-secondary mt-1">提交时间：{escape(current_request.get('created_on') or '未知')}</div>
            </div>
            <form method="post" action="/team-center" class="m-0">
              <input type="hidden" name="action" value="cancel_request">
              <button type="submit" class="btn btn-outline-dark">取消认领申请</button>
            </form>
          </div>
        </section>
        """

    review_rows: list[str] = []
    for item in requests:
        if item.get("request_type") != "team_claim":
            continue
        target_team = get_team_by_id(data, str(item.get("target_team_id") or "").strip())
        if not can_review_team_claim_request(data, current_user, target_team):
            continue
        review_rows.append(
            f"""
            <tr>
              <td>{escape(item['display_name'])}</td>
              <td>{escape(item['username'])}</td>
              <td>{escape(target_team['name'] if target_team else item.get('target_team_id', ''))}</td>
              <td>{escape(team_scope_label(target_team) if target_team else ((item.get('scope_competition_name') or '') + ' / ' + (item.get('scope_season_name') or '')))}</td>
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

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">战队认领中心</div>
      <h1 class="display-6 fw-semibold mb-3">赛季战队认领与身份切换</h1>
      <p class="mb-0 opacity-75">战队名字和成员全部跟随赛季档案。认领负责人只负责维护战队的展示信息，例如图标、简介和赛段分组。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">我的赛季身份</h2>
          <p class="section-copy mb-0">账号可以绑定多个赛季参赛档案。这里用于切换主身份，并进入对应战队页维护你已认领的战队展示信息。</p>
        </div>
      </div>
      <div class="row g-3">{''.join(identity_cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">当前账号还没有已绑定的赛季身份。</div></div>'}</div>
    </section>
    {pending_panel}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">赛季战队认领</h2>
          <p class="section-copy mb-0">赛季战队由管理员批量创建，或在录入比赛时自动生成。账号侧不再创建战队，只能认领尚未负责的赛季战队。</p>
        </div>
      </div>
      <div class="row g-3">{''.join(claim_cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">当前没有可认领的战队，或你在这些赛事赛季里已经拥有身份。</div></div>'}</div>
    </section>
    {(
      f'''
      <section class="panel shadow-sm p-3 p-lg-4">
        <h2 class="section-title mb-2">待审核的战队认领申请</h2>
        <p class="section-copy mb-3">管理员或对应赛事管理员可以审核赛季战队的认领申请。</p>
        <div class="table-responsive">
          <table class="table align-middle">
            <thead>
              <tr>
                <th>申请人</th>
                <th>账号</th>
                <th>目标战队</th>
                <th>赛事赛季</th>
                <th>申请时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>{''.join(review_rows)}</tbody>
          </table>
        </div>
      </section>
      '''
      if review_rows
      else ''
    )}
    """
    return layout("战队认领", body, ctx, alert=alert)


def handle_team_center_impl(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_team_center_page_impl(ctx))

    current_user = ctx.current_user
    if not current_user:
        return redirect(start_response, "/login?next=/team-center")

    action = form_value(ctx.form, "action").strip()
    data = load_validated_data()
    users = load_users()
    requests = load_membership_requests()
    current_player = get_user_player(data, current_user)

    if action == "switch_primary_identity":
        return handle_switch_primary_identity_action(
            ctx,
            start_response,
            data,
            users,
            current_user,
        )

    if action == "request_team_claim":
        next_path = form_value(ctx.form, "next").strip()
        current_request = next(
            (
                item
                for item in requests
                if item.get("username") == current_user["username"]
                and item.get("request_type") == "team_claim"
            ),
            None,
        )
        if current_request:
            return _respond_with_alert(start_response, ctx, "你当前已经有一条待处理的战队认领申请。", next_path)
        team_id = form_value(ctx.form, "team_id").strip()
        target_team = get_team_by_id(data, team_id)
        if not target_team:
            return _respond_with_alert(start_response, ctx, "没有找到要认领的战队。", next_path)
        if not is_unclaimed_team(target_team):
            return _respond_with_alert(start_response, ctx, "这支战队已经被认领，不能重复申请。", next_path)
        if get_team_season_status(data, target_team) == "completed":
            return _respond_with_alert(start_response, ctx, "已结束赛季的战队不再开放认领。", next_path)
        competition_name, season_name = get_team_scope(target_team)
        if user_has_team_identity_in_scope(data, current_user, competition_name, season_name):
            return _respond_with_alert(start_response, ctx, "当前账号在这个赛事赛季里已经有战队身份，不能重复认领。", next_path)
        requests.append(
            {
                "request_id": secrets.token_urlsafe(12),
                "request_type": "team_claim",
                "username": current_user["username"],
                "display_name": current_user.get("display_name") or current_user["username"],
                "player_id": "",
                "source_team_id": "",
                "target_team_id": team_id,
                "target_guild_id": "",
                "scope_competition_name": competition_name,
                "scope_season_name": season_name,
                "request_payload": {},
                "created_on": legacy.china_now_label(),
            }
        )
        save_membership_requests(requests)
        return _respond_with_alert(start_response, ctx, "认领申请已提交，等待管理员或赛事管理员审核。", next_path)

    if action == "cancel_request":
        requests = [
            item
            for item in requests
            if not (
                item.get("username") == current_user["username"]
                and item.get("request_type") == "team_claim"
            )
        ]
        save_membership_requests(requests)
        return start_response_html(start_response, "200 OK", get_team_center_page_impl(ctx, alert="认领申请已取消。"))

    if action in {"approve_team_claim", "reject_team_claim"}:
        request_id = form_value(ctx.form, "request_id").strip()
        request_item = next(
            (
                item
                for item in requests
                if item.get("request_id") == request_id
                and item.get("request_type") == "team_claim"
            ),
            None,
        )
        if not request_item:
            return start_response_html(start_response, "200 OK", get_team_center_page_impl(ctx, alert="没有找到对应的战队认领申请。"))
        target_team = get_team_by_id(data, str(request_item.get("target_team_id") or "").strip())
        if not can_review_team_claim_request(data, current_user, target_team):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">你没有权限审核这条战队认领申请。</div>', ctx),
            )
        if action == "reject_team_claim":
            requests = [item for item in requests if item.get("request_id") != request_id]
            save_membership_requests(requests)
            return start_response_html(start_response, "200 OK", get_team_center_page_impl(ctx, alert="战队认领申请已拒绝。"))

        requester = next((user for user in users if user["username"] == request_item["username"]), None)
        if not requester or not target_team or not is_unclaimed_team(target_team):
            requests = [item for item in requests if item.get("request_id") != request_id]
            save_membership_requests(requests)
            return start_response_html(start_response, "200 OK", get_team_center_page_impl(ctx, alert="认领申请对应的数据已失效，申请已移除。"))
        competition_name, season_name = get_team_scope(target_team)
        if user_has_team_identity_in_scope(data, requester, competition_name, season_name):
            requests = [item for item in requests if item.get("request_id") != request_id]
            save_membership_requests(requests)
            return start_response_html(start_response, "200 OK", get_team_center_page_impl(ctx, alert="该账号在当前赛事赛季里已经有战队身份，申请已移除。"))

        existing_player_ids = {player["player_id"] for player in data["players"]}
        captain_player = find_player_by_name_in_scope(
            data,
            competition_name,
            season_name,
            requester.get("display_name") or requester["username"],
            target_team["name"],
        )
        if captain_player is None:
            player_id = build_unique_slug(existing_player_ids, "player", requester["username"], "player")
            captain_player = build_placeholder_player(
                player_id,
                target_team["team_id"],
                competition_name,
                season_name,
                display_name=requester.get("display_name") or requester["username"],
            )
            captain_player["notes"] = "经管理员审核通过后认领赛季战队时创建的负责人档案。"
            data["players"].append(captain_player)
        if captain_player["player_id"] not in target_team["members"]:
            target_team["members"].append(captain_player["player_id"])
        target_team["captain_player_id"] = captain_player["player_id"]
        users = append_user_player_binding(users, requester["username"], captain_player["player_id"])
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(start_response, "200 OK", get_team_center_page_impl(ctx, alert="通过认领申请失败：" + "；".join(errors[:3])))
        requests = [item for item in requests if item.get("request_id") != request_id]
        save_membership_requests(requests)
        return start_response_html(start_response, "200 OK", get_team_center_page_impl(ctx, alert=f"已通过 {target_team['name']} 的认领申请。"))

    if action == "update_team_profile":
        team_id = form_value(ctx.form, "team_id").strip()
        next_path = form_value(ctx.form, "next").strip()
        team = get_team_by_id(data, team_id)
        if not team:
            return _respond_with_alert(start_response, ctx, "没有找到要编辑的战队。", next_path)
        if not can_manage_team(ctx, team, current_player):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">只有管理员、具备战队管理权限的账号或已认领该战队的负责人可以编辑战队资料。</div>', ctx),
            )
        if get_team_season_status(data, team) == "completed":
            return _respond_with_alert(start_response, ctx, "当前战队所属赛季已结束，战队资料已锁定。", next_path)
        short_name = form_value(ctx.form, "short_name").strip() or str(team.get("short_name") or "").strip() or team["name"][:12]
        team["short_name"] = short_name
        team["notes"] = form_value(ctx.form, "notes").strip()
        errors = save_repository_state(data, users)
        if errors:
            return _respond_with_alert(start_response, ctx, "保存战队资料失败：" + "；".join(errors[:3]), next_path)
        return _respond_with_alert(start_response, ctx, "战队资料已更新。", next_path)

    if action == "update_team_stage_groups":
        team_id = form_value(ctx.form, "team_id").strip()
        team = get_team_by_id(data, team_id)
        if not team:
            return start_response_html(start_response, "200 OK", get_team_center_page_impl(ctx, alert="没有找到要更新分组信息的战队。"))
        if not can_manage_team(ctx, team, current_player):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">只有管理员、具备战队管理权限的账号或已认领该战队的负责人可以维护战队分组。</div>', ctx),
            )
        if get_team_season_status(data, team) == "completed":
            return start_response_html(start_response, "200 OK", legacy.get_team_page(ctx, team_id, alert="当前战队所属赛季已结束，战队分组信息已锁定。"))
        team["stage_groups"] = collect_team_stage_groups_from_form(ctx.form)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(start_response, "200 OK", legacy.get_team_page(ctx, team_id, alert="保存战队分组失败：" + "；".join(errors[:3])))
        return start_response_html(start_response, "200 OK", legacy.get_team_page(ctx, team_id, alert="战队分组信息已更新。"))

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
            return start_response_html(start_response, "200 OK", get_team_center_page_impl(ctx, alert="没有找到要删除的战队。"))
        dissolution_error = get_team_dissolution_error(data, team, "删除战队")
        if dissolution_error:
            return start_response_html(start_response, "200 OK", get_team_center_page_impl(ctx, alert=dissolution_error))
        users, requests = dissolve_team(data, users, team)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(start_response, "200 OK", get_team_center_page_impl(ctx, alert="删除战队失败：" + "；".join(errors[:3])))
        save_membership_requests(requests)
        return start_response_html(start_response, "200 OK", get_team_center_page_impl(ctx, alert=f"战队 {team['name']} 已删除。"))

    return start_response_html(start_response, "200 OK", get_team_center_page_impl(ctx, alert="未识别的操作。"))
