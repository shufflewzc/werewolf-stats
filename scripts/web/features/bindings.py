from __future__ import annotations

from html import escape

import web_app as legacy
import secrets

RequestContext = legacy.RequestContext
add_user_linked_player_id = legacy.add_user_linked_player_id
build_bound_player_summary = legacy.build_bound_player_summary
build_player_binding_candidates = legacy.build_player_binding_candidates
build_profile_binding_summary = legacy.build_profile_binding_summary
can_manage_player_bindings = legacy.can_manage_player_bindings
china_now_label = legacy.china_now_label
find_season_binding_conflict = legacy.find_season_binding_conflict
form_value = legacy.form_value
get_player_binding_scope_labels = legacy.get_player_binding_scope_labels
get_team_by_id = legacy.get_team_by_id
get_user_bound_player_ids = legacy.get_user_bound_player_ids
get_user_by_player_id = legacy.get_user_by_player_id
get_user_badge_label = legacy.get_user_badge_label
is_admin_user = legacy.is_admin_user
layout = legacy.layout
load_membership_requests = legacy.load_membership_requests
load_users = legacy.load_users
load_validated_data = legacy.load_validated_data
redirect = legacy.redirect
remove_user_linked_player_id = legacy.remove_user_linked_player_id
save_membership_requests = legacy.save_membership_requests
save_repository_state = legacy.save_repository_state
start_response_html = legacy.start_response_html
user_has_permission = legacy.user_has_permission


def can_review_binding_requests(data, acting_user, target_user, source_player) -> bool:
    if not acting_user or not target_user or not source_player:
        return False
    del data, target_user, source_player
    return bool(
        is_admin_user(acting_user)
        or user_has_permission(acting_user, "player_binding_manage")
    )


def can_manage_other_binding_accounts(data, acting_user) -> bool:
    del data
    if not acting_user:
        return False
    return (
        is_admin_user(acting_user)
        or user_has_permission(acting_user, "player_binding_manage")
    )


def can_direct_bind_player_ids(acting_user) -> bool:
    return bool(acting_user and is_admin_user(acting_user))


def get_player_bindings_page(
    ctx: RequestContext,
    alert: str = "",
    target_username: str = "",
    selected_player_id: str = "",
) -> str:
    if not ctx.current_user:
        return layout("未登录", '<div class="alert alert-danger">请先登录后再管理绑定关系。</div>', ctx)
    data = load_validated_data()
    users = load_users()
    selected_player_id = selected_player_id.strip() or form_value(ctx.query, "player_id").strip()
    selected_player = next(
        (player for player in data["players"] if player["player_id"] == selected_player_id),
        None,
    )
    requested_target_name = (
        target_username.strip()
        or form_value(ctx.query, "username").strip()
    )
    target_name = ctx.current_user["username"]
    if requested_target_name and can_manage_other_binding_accounts(data, ctx.current_user):
        target_name = requested_target_name
    target_user = next((user for user in users if user["username"] == target_name), None)
    if not target_user:
        return layout("未找到账号", '<div class="alert alert-danger">没有找到要绑定的账号。</div>', ctx)
    if not can_manage_player_bindings(data, ctx.current_user, target_user, selected_player):
        return layout("没有权限", '<div class="alert alert-danger">你没有权限管理该账号的赛事绑定。</div>', ctx)
    target_username_input = (
        f'<input type="hidden" name="target_username" value="{escape(target_user["username"])}">'
        if target_user["username"] != ctx.current_user["username"]
        else ""
    )
    summary = build_bound_player_summary(data, target_user)
    candidates = build_player_binding_candidates(data, users, target_user)
    requests = load_membership_requests()
    pending_request_map = {
        item.get("player_id", ""): item
        for item in requests
        if item.get("request_type") == "player_binding"
        and item.get("username") == target_user["username"]
    }
    bound_rows = []
    for player_id in get_user_bound_player_ids(target_user):
        player = next((item for item in data["players"] if item["player_id"] == player_id), None)
        scope_labels = "、".join(get_player_binding_scope_labels(data, player_id)) or "暂无比赛范围"
        team_name = (
            get_team_by_id(data, player["team_id"])["name"]
            if player and get_team_by_id(data, player["team_id"])
            else (player["team_id"] if player else "未知战队")
        )
        action_html = (
            '<span class="small text-secondary">当前主身份</span>'
            if target_user.get("player_id") == player_id
            else f"""
            <form method="post" action="/bindings" class="m-0">
              <input type="hidden" name="action" value="unbind_player_id">
              {target_username_input}
              <input type="hidden" name="player_id" value="{escape(player_id)}">
              <button type="submit" class="btn btn-sm btn-outline-danger">解绑</button>
            </form>
            """
        )
        bound_rows.append(
            f"""
            <tr>
              <td>{escape(player_id)}</td>
              <td>{escape(player['display_name']) if player else '未找到档案'}</td>
              <td>{escape(scope_labels)}</td>
              <td>{escape(team_name)}</td>
              <td>{action_html}</td>
            </tr>
            """
        )
    candidate_rows = []
    for item in candidates:
        owner_hint = ""
        if item["owner_username"] and item["owner_username"] != target_user["username"]:
            owner_hint = f'<div class="small text-secondary">当前归属：{escape(item["owner_username"])}</div>'
        action_html = (
            '<span class="small text-secondary">已绑定到当前账号</span>'
            if item["already_bound"]
            else (
                f"""
                <form method="post" action="/bindings" class="m-0">
                  <input type="hidden" name="action" value="direct_bind_player_id">
                  {target_username_input}
                  <input type="hidden" name="player_id" value="{escape(item['player_id'])}">
                  <button type="submit" class="btn btn-sm btn-dark">直接绑定</button>
                </form>
                """
                if can_direct_bind_player_ids(ctx.current_user)
                else (
                '<span class="small text-secondary">绑定申请审批中</span>'
                if item["player_id"] in pending_request_map
                else f"""
                <form method="post" action="/bindings" class="m-0">
                  <input type="hidden" name="action" value="request_bind_player_id">
                  {target_username_input}
                  <input type="hidden" name="player_id" value="{escape(item['player_id'])}">
                  <button type="submit" class="btn btn-sm btn-dark">提交绑定申请</button>
                </form>
                """
                )
            )
        )
        row_class = "table-active" if item["player_id"] == selected_player_id else ""
        candidate_rows.append(
            f"""
            <tr class="{row_class}">
              <td>{escape(item['player_id'])}</td>
              <td>{escape(item['display_name'])}</td>
              <td>{escape(item['team_name'])}</td>
              <td>{item['games_played']}</td>
              <td>{escape(item['scope_labels'])}</td>
              <td>{owner_hint}{action_html}</td>
            </tr>
            """
        )
    pending_rows = []
    for item in requests:
        if item.get("request_type") != "player_binding":
            continue
        pending_player_id = str(item.get("player_id") or "").strip()
        pending_target_user = next((user for user in users if user["username"] == item["username"]), None)
        pending_player = next((player for player in data["players"] if player["player_id"] == pending_player_id), None)
        if not pending_target_user or not pending_player:
            continue
        if not can_review_binding_requests(data, ctx.current_user, pending_target_user, pending_player):
            continue
        pending_rows.append(
            f"""
            <tr>
              <td>{escape(item['display_name'])}</td>
              <td>{escape(item['username'])}</td>
              <td>{escape(pending_player_id)}</td>
              <td>{escape(pending_player.get('display_name') or pending_player_id)}</td>
              <td>{escape('、'.join(get_player_binding_scope_labels(data, pending_player_id)) or '暂无比赛范围')}</td>
              <td>{escape(item.get('created_on') or '')}</td>
              <td>
                <div class="d-flex flex-wrap gap-2">
                  <form method="post" action="/bindings" class="m-0">
                    <input type="hidden" name="action" value="approve_binding_request">
                    <input type="hidden" name="request_id" value="{escape(item['request_id'])}">
                    <button type="submit" class="btn btn-sm btn-dark">通过</button>
                  </form>
                  <form method="post" action="/bindings" class="m-0">
                    <input type="hidden" name="action" value="reject_binding_request">
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
      <div class="eyebrow mb-3">赛事数据绑定</div>
      <h1 class="display-6 fw-semibold mb-3">管理参赛ID与账号绑定</h1>
      <p class="mb-0 opacity-75">比赛录入时，系统会先为选手创建赛季参赛档案。账号注册后只需要把账号绑定到这些赛季档案上，个人生涯数据就会按已绑定档案聚合展示；赛季原始档案会一直保留。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">当前账号</h2>
          <p class="section-copy mb-0">当前正在为 <strong>{escape(target_user['username'])}</strong> 维护绑定关系。页面只保留绑定与解绑操作；管理员或具备权限的账号可通过指定用户名进入他人的绑定页。</p>
        </div>
        <a class="btn btn-outline-dark" href="/profile">返回个人中心</a>
      </div>
      {build_profile_binding_summary(summary) if summary else '<div class="alert alert-secondary mb-0">该账号暂时还没有已绑定的赛事数据。</div>'}
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h2 class="section-title mb-2">当前已绑定ID</h2>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>赛季参赛ID</th>
              <th>档案名称</th>
              <th>覆盖赛季</th>
              <th>当前战队</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>{''.join(bound_rows) or '<tr><td colspan="5" class="text-secondary">当前还没有绑定任何赛季参赛ID。</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <h2 class="section-title mb-2">可绑定的赛季参赛ID</h2>
      <p class="section-copy mb-3">这里只展示已有比赛记录、且尚未绑定到其他账号的赛季参赛ID档案。提交绑定申请后，再由管理员或具备绑定权限的赛事管理员审批。</p>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>赛季参赛ID</th>
              <th>档案名称</th>
              <th>战队</th>
              <th>出场</th>
              <th>覆盖范围</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>{''.join(candidate_rows) or '<tr><td colspan="6" class="text-secondary">当前没有可绑定的赛季参赛ID。</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    {(
      f'''
      <section class="panel shadow-sm p-3 p-lg-4 mt-4">
        <h2 class="section-title mb-2">待审批绑定申请</h2>
        <div class="table-responsive">
          <table class="table align-middle">
            <thead>
              <tr>
                <th>申请显示名</th>
                <th>申请账号</th>
                <th>参赛ID</th>
                <th>档案名称</th>
                <th>覆盖范围</th>
                <th>申请时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>{''.join(pending_rows)}</tbody>
          </table>
        </div>
      </section>
      '''
      if pending_rows
      else ''
    )}
    """
    return layout("赛事数据绑定", body, ctx, alert=alert)


def handle_player_bindings(ctx: RequestContext, start_response):
    if not ctx.current_user:
        return redirect(start_response, "/login?next=/bindings")
    if ctx.method == "GET":
        return start_response_html(
            start_response,
            "200 OK",
            get_player_bindings_page(
                ctx,
                target_username=form_value(ctx.query, "username").strip(),
                selected_player_id=form_value(ctx.query, "player_id").strip(),
            ),
        )

    data = load_validated_data()
    users = load_users()
    action = form_value(ctx.form, "action").strip()
    target_username = ctx.current_user["username"]
    requested_target_username = form_value(ctx.form, "target_username").strip()
    if requested_target_username and can_manage_other_binding_accounts(data, ctx.current_user):
        target_username = requested_target_username
    player_id = form_value(ctx.form, "player_id").strip()
    target_user = next((user for user in users if user["username"] == target_username), None)
    if not target_user:
        return start_response_html(
            start_response,
            "200 OK",
            get_player_bindings_page(ctx, alert="没有找到要绑定的账号。"),
        )

    if action == "request_bind_player_id":
        source_player = next((player for player in data["players"] if player["player_id"] == player_id), None)
        if not source_player:
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert="没有找到对应的参赛ID档案。",
                    target_username=target_username,
                ),
            )
        if not can_manage_player_bindings(data, ctx.current_user, target_user, source_player):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">你没有权限操作这条绑定关系。</div>', ctx),
            )
        owner_user = get_user_by_player_id(users, player_id)
        if owner_user and owner_user["username"] != target_user["username"]:
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert=f"参赛ID {player_id} 已经绑定到账号 {get_user_badge_label(owner_user)}。",
                    target_username=target_username,
                    selected_player_id=player_id,
                ),
            )
        season_conflict = find_season_binding_conflict(data, target_user, player_id)
        if season_conflict:
            conflict_player_id, conflict_scopes = season_conflict
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert=(
                        f"账号 {target_username} 已经绑定赛季参赛ID {conflict_player_id}，"
                        f"覆盖范围：{'、'.join(conflict_scopes)}。同一赛季只需要绑定一个ID。"
                    ),
                    target_username=target_username,
                    selected_player_id=player_id,
                ),
            )
        requests = load_membership_requests()
        if any(
            item.get("request_type") == "player_binding"
            and item.get("username") == target_username
            and item.get("player_id") == player_id
            for item in requests
        ):
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert="这条绑定申请已经提交，等待审批。",
                    target_username=target_username,
                    selected_player_id=player_id,
                ),
            )
        requests.append(
            {
                "request_id": secrets.token_urlsafe(12),
                "request_type": "player_binding",
                "username": target_username,
                "display_name": target_user.get("display_name") or target_username,
                "player_id": player_id,
                "source_team_id": source_player.get("team_id"),
                "target_team_id": source_player.get("team_id"),
                "target_guild_id": "",
                "scope_competition_name": "",
                "scope_season_name": "",
                "created_on": china_now_label(),
            }
        )
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_player_bindings_page(
                ctx,
                alert="绑定申请已提交，等待管理员或具备绑定权限的赛事管理员审批。",
                target_username=target_username,
                selected_player_id=player_id,
            ),
        )

    if action == "direct_bind_player_id":
        if not can_direct_bind_player_ids(ctx.current_user):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">只有管理员可以直接绑定参赛ID。</div>', ctx),
            )
        source_player = next((player for player in data["players"] if player["player_id"] == player_id), None)
        if not source_player:
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert="没有找到对应的参赛ID档案。",
                    target_username=target_username,
                ),
            )
        if not can_manage_player_bindings(data, ctx.current_user, target_user, source_player):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">你没有权限操作这条绑定关系。</div>', ctx),
            )
        season_conflict = find_season_binding_conflict(data, target_user, player_id)
        if season_conflict:
            conflict_player_id, conflict_scopes = season_conflict
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert=(
                        f"账号 {target_username} 已经绑定赛季参赛ID {conflict_player_id}，"
                        f"覆盖范围：{'、'.join(conflict_scopes)}。同一赛季只需要绑定一个ID。"
                    ),
                    target_username=target_username,
                    selected_player_id=player_id,
                ),
            )
        owner_user = get_user_by_player_id(users, player_id)
        if owner_user and owner_user["username"] != target_user["username"]:
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert=f"参赛ID {player_id} 已经绑定到账号 {get_user_badge_label(owner_user)}。",
                    target_username=target_username,
                    selected_player_id=player_id,
                ),
            )
        users = add_user_linked_player_id(users, target_username, player_id)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert="直接绑定失败：" + "；".join(errors[:3]),
                    target_username=target_username,
                    selected_player_id=player_id,
                ),
            )
        requests = [
            item
            for item in load_membership_requests()
            if not (
                item.get("request_type") == "player_binding"
                and item.get("username") == target_username
                and item.get("player_id") == player_id
            )
        ]
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_player_bindings_page(
                ctx,
                alert=f"已直接为账号 {target_username} 绑定参赛ID {player_id}。",
                target_username=target_username,
                selected_player_id=player_id,
            ),
        )

    if action == "approve_binding_request":
        request_id = form_value(ctx.form, "request_id").strip()
        requests = load_membership_requests()
        request_item = next(
            (
                item
                for item in requests
                if item.get("request_id") == request_id and item.get("request_type") == "player_binding"
            ),
            None,
        )
        if not request_item:
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(ctx, alert="没有找到对应的绑定申请。"),
            )
        request_target_user = next((user for user in users if user["username"] == request_item["username"]), None)
        request_player_id = str(request_item.get("player_id") or "").strip()
        request_player = next((player for player in data["players"] if player["player_id"] == request_player_id), None)
        if not can_review_binding_requests(data, ctx.current_user, request_target_user, request_player):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">你没有权限审批这条绑定申请。</div>', ctx),
            )
        if not request_target_user or not request_player:
            requests = [item for item in requests if item.get("request_id") != request_id]
            save_membership_requests(requests)
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(ctx, alert="绑定申请对应的数据已失效，申请已移除。"),
            )
        season_conflict = find_season_binding_conflict(data, request_target_user, request_player_id)
        if season_conflict:
            conflict_player_id, conflict_scopes = season_conflict
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert=(
                        f"审批失败：账号 {request_target_user['username']} 已经绑定赛季参赛ID {conflict_player_id}，"
                        f"覆盖范围：{'、'.join(conflict_scopes)}。"
                    ),
                    target_username=request_target_user["username"],
                    selected_player_id=request_player_id,
                ),
            )
        owner_user = get_user_by_player_id(users, request_player_id)
        if owner_user and owner_user["username"] != request_target_user["username"]:
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert=f"审批失败：参赛ID {request_player_id} 已绑定到 {get_user_badge_label(owner_user)}。",
                    target_username=request_target_user["username"],
                    selected_player_id=request_player_id,
                ),
            )
        users = add_user_linked_player_id(users, request_target_user["username"], request_player_id)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert="审批绑定失败：" + "；".join(errors[:3]),
                    target_username=request_target_user["username"],
                    selected_player_id=request_player_id,
                ),
            )
        requests = [item for item in requests if item.get("request_id") != request_id]
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_player_bindings_page(
                ctx,
                alert=f"已通过账号 {request_target_user['username']} 对参赛ID {request_player_id} 的绑定申请。",
                target_username=request_target_user["username"],
                selected_player_id=request_player_id,
            ),
        )

    if action == "reject_binding_request":
        request_id = form_value(ctx.form, "request_id").strip()
        requests = load_membership_requests()
        request_item = next(
            (
                item
                for item in requests
                if item.get("request_id") == request_id and item.get("request_type") == "player_binding"
            ),
            None,
        )
        if not request_item:
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(ctx, alert="没有找到对应的绑定申请。"),
            )
        request_target_user = next((user for user in users if user["username"] == request_item["username"]), None)
        request_player = next((player for player in data["players"] if player["player_id"] == request_item.get("player_id")), None)
        if not can_review_binding_requests(data, ctx.current_user, request_target_user, request_player):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">你没有权限审批这条绑定申请。</div>', ctx),
            )
        requests = [item for item in requests if item.get("request_id") != request_id]
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_player_bindings_page(ctx, alert="绑定申请已拒绝。"),
        )

    if action == "unbind_player_id":
        source_player = next((player for player in data["players"] if player["player_id"] == player_id), None)
        if not source_player:
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert="没有找到对应的参赛ID档案。",
                    target_username=target_username,
                ),
            )
        if not can_manage_player_bindings(data, ctx.current_user, target_user, source_player):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">你没有权限操作这条绑定关系。</div>', ctx),
            )
        if target_user.get("player_id") == player_id:
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert="当前主身份不能直接解绑；如需变更，请联系管理员处理。",
                    target_username=target_username,
                    selected_player_id=player_id,
                ),
            )
        users = remove_user_linked_player_id(users, target_username, player_id)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert="解绑失败：" + "；".join(errors[:3]),
                    target_username=target_username,
                    selected_player_id=player_id,
                ),
            )
        return start_response_html(
            start_response,
            "200 OK",
            get_player_bindings_page(
                ctx,
                alert=f"已解除账号 {target_username} 与参赛ID {player_id} 的绑定。",
                target_username=target_username,
                selected_player_id=player_id,
            ),
        )

    return start_response_html(
        start_response,
        "200 OK",
        get_player_bindings_page(
            ctx,
            alert="未识别的绑定操作。",
            target_username=target_username,
        ),
    )
