from __future__ import annotations

from html import escape

import web_app as legacy

RequestContext = legacy.RequestContext
add_user_linked_player_id = legacy.add_user_linked_player_id
build_bound_player_summary = legacy.build_bound_player_summary
build_player_binding_candidates = legacy.build_player_binding_candidates
build_profile_binding_summary = legacy.build_profile_binding_summary
can_manage_player_bindings = legacy.can_manage_player_bindings
find_season_binding_conflict = legacy.find_season_binding_conflict
form_value = legacy.form_value
get_player_binding_scope_labels = legacy.get_player_binding_scope_labels
get_team_by_id = legacy.get_team_by_id
get_user_bound_player_ids = legacy.get_user_bound_player_ids
get_user_by_player_id = legacy.get_user_by_player_id
is_admin_user = legacy.is_admin_user
is_team_captain_user = legacy.is_team_captain_user
layout = legacy.layout
load_users = legacy.load_users
load_validated_data = legacy.load_validated_data
redirect = legacy.redirect
remove_user_linked_player_id = legacy.remove_user_linked_player_id
save_repository_state = legacy.save_repository_state
start_response_html = legacy.start_response_html
user_has_permission = legacy.user_has_permission


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
    target_name = target_username.strip() or form_value(ctx.query, "username").strip() or ctx.current_user["username"]
    target_user = next((user for user in users if user["username"] == target_name), None)
    if not target_user:
        return layout("未找到账号", '<div class="alert alert-danger">没有找到要绑定的账号。</div>', ctx)
    if not can_manage_player_bindings(data, ctx.current_user, target_user, selected_player):
        return layout("没有权限", '<div class="alert alert-danger">你没有权限管理该账号的赛事绑定。</div>', ctx)
    summary = build_bound_player_summary(data, target_user)
    candidates = build_player_binding_candidates(data, users, target_user)
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
              <input type="hidden" name="target_username" value="{escape(target_user['username'])}">
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
        action_html = (
            '<span class="small text-secondary">已绑定到当前账号</span>'
            if item["already_bound"]
            else f"""
            <form method="post" action="/bindings" class="m-0">
              <input type="hidden" name="action" value="bind_player_id">
              <input type="hidden" name="target_username" value="{escape(target_user['username'])}">
              <input type="hidden" name="player_id" value="{escape(item['player_id'])}">
              <button type="submit" class="btn btn-sm btn-dark">绑定到该账号</button>
            </form>
            """
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
              <td>{action_html}</td>
            </tr>
            """
        )
    username_picker_html = ""
    if (
        is_admin_user(ctx.current_user)
        or user_has_permission(ctx.current_user, "player_binding_manage")
        or is_team_captain_user(data, ctx.current_user)
    ):
        username_picker_html = f"""
        <form method="get" action="/bindings" class="row g-3 align-items-end mb-4">
          <div class="col-12 col-lg-5">
            <label class="form-label">目标账号</label>
            <input class="form-control" name="username" value="{escape(target_user['username'])}" placeholder="输入用户名">
          </div>
          <div class="col-12 col-lg-4">
            <label class="form-label">预选参赛ID</label>
            <input class="form-control" name="player_id" value="{escape(selected_player_id)}" placeholder="例如 p001-s1">
          </div>
          <div class="col-12 col-lg-3">
            <button type="submit" class="btn btn-outline-dark w-100">切换绑定对象</button>
          </div>
        </form>
        """
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">赛事数据绑定</div>
      <h1 class="display-6 fw-semibold mb-3">管理参赛ID与账号绑定</h1>
      <p class="mb-0 opacity-75">比赛录入时如果选手还没注册，系统会先为赛季参赛ID预留档案。后续只要把该赛季ID绑定一次，这个赛季下的全部比赛就会自动归到该账号名下；不同赛季则可以继续绑定不同ID。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">目标账号</h2>
          <p class="section-copy mb-0">当前正在为 <strong>{escape(target_user['username'])}</strong> 维护绑定关系。</p>
        </div>
        <a class="btn btn-outline-dark" href="/profile">返回个人中心</a>
      </div>
      {username_picker_html}
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
      <p class="section-copy mb-3">这里只展示已有比赛记录、且尚未绑定到其他账号的赛季参赛ID档案。同一账号在同一赛事赛季内只需要绑定一个ID。</p>
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
    target_username = form_value(ctx.form, "target_username").strip() or ctx.current_user["username"]
    player_id = form_value(ctx.form, "player_id").strip()
    target_user = next((user for user in users if user["username"] == target_username), None)
    source_player = next((player for player in data["players"] if player["player_id"] == player_id), None)
    if not target_user:
        return start_response_html(
            start_response,
            "200 OK",
            get_player_bindings_page(ctx, alert="没有找到要绑定的账号。"),
        )
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
                alert=f"参赛ID {player_id} 已经绑定到账号 {owner_user['username']}。",
                target_username=target_username,
                selected_player_id=player_id,
            ),
        )

    if action == "bind_player_id":
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
        users = add_user_linked_player_id(users, target_username, player_id)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert="保存绑定失败：" + "；".join(errors[:3]),
                    target_username=target_username,
                    selected_player_id=player_id,
                ),
            )
        return start_response_html(
            start_response,
            "200 OK",
            get_player_bindings_page(
                ctx,
                alert=f"已将参赛ID {player_id} 绑定到账号 {target_username}。",
                target_username=target_username,
                selected_player_id=player_id,
            ),
        )

    if action == "unbind_player_id":
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
