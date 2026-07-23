from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import urlencode

import web_app as legacy

ACCOUNT_ROLE_OPTIONS = legacy.ACCOUNT_ROLE_OPTIONS
ADMIN_USERNAME = legacy.ADMIN_USERNAME
DEFAULT_PROVINCE_NAME = legacy.DEFAULT_PROVINCE_NAME
EVENT_SCOPE_PERMISSION_KEYS = legacy.EVENT_SCOPE_PERMISSION_KEYS
PERMISSION_GROUPS = legacy.PERMISSION_GROUPS
PERMISSION_LABELS = legacy.PERMISSION_LABELS
RequestContext = legacy.RequestContext
account_role_label = legacy.account_role_label
audit_action = legacy.audit_action
build_manager_scope_options = legacy.build_manager_scope_options
form_value = legacy.form_value
get_all_permission_keys = legacy.get_all_permission_keys
get_manager_scope_labels = legacy.get_manager_scope_labels
get_user_manager_scope_keys = legacy.get_user_manager_scope_keys
get_user_permission_labels = legacy.get_user_permission_labels
get_user_region_label = legacy.get_user_region_label
hash_password = legacy.hash_password
is_admin_user = legacy.is_admin_user
layout = legacy.layout
load_dashboard_activity_settings = legacy.load_dashboard_activity_settings
load_users = legacy.load_users
normalize_permission_keys = legacy.normalize_permission_keys
normalize_user_location = legacy.normalize_user_location
option_tags = legacy.option_tags
require_admin = legacy.require_admin
revoke_user_sessions = legacy.revoke_user_sessions
save_dashboard_activity_settings = legacy.save_dashboard_activity_settings
save_users = legacy.save_users
start_response_html = legacy.start_response_html
validate_account_form = legacy.validate_account_form
validate_account_update_form = legacy.validate_account_update_form
validate_permission_assignment = legacy.validate_permission_assignment


def get_accounts_page(
    ctx: RequestContext,
    alert: str = "",
    form_values: dict[str, str] | None = None,
) -> str:
    activity_settings = load_dashboard_activity_settings()
    current_form = form_values or {
        "editing_username": "",
        "username": "",
        "display_name": "",
        "role": "member",
        "province_name": DEFAULT_PROVINCE_NAME,
        "region_name": "广州市",
        "manager_scope_keys": [],
    }
    activity_mode = str((form_values or {}).get("activity_mode") or activity_settings.get("mode") or "auto").strip()
    activity_custom_text = str((form_values or {}).get("activity_custom_text") or "").strip()
    if not activity_custom_text:
        activity_custom_text = "\n".join(
            " | ".join(
                [
                    str(item.get("label") or "手动动态"),
                    str(item.get("time_label") or "管理员编辑"),
                    str(item.get("text") or ""),
                    str(item.get("href") or "/competitions"),
                ]
            )
            for item in activity_settings.get("items", [])
        )
    users = load_users()
    data = legacy.load_validated_data()
    requested_edit_username = str(current_form.get("editing_username") or "").strip()
    if not requested_edit_username:
        requested_edit_username = form_value(ctx.query, "edit_username").strip()
    editing_user = next(
        (user for user in users if user["username"] == requested_edit_username),
        None,
    )
    if editing_user and not form_values:
        current_form.update(
            {
                "editing_username": editing_user["username"],
                "username": editing_user["username"],
                "display_name": editing_user.get("display_name") or editing_user["username"],
                "role": editing_user.get("role") or "member",
                "province_name": editing_user.get("province_name") or DEFAULT_PROVINCE_NAME,
                "region_name": editing_user.get("region_name") or "广州市",
                "manager_scope_keys": list(editing_user.get("manager_scope_keys", [])),
            }
        )
    editing_account = bool(str(current_form.get("editing_username") or "").strip())
    total_accounts = len(users)
    active_accounts = sum(1 for user in users if user.get("active"))
    manager_accounts = sum(1 for user in users if user.get("role") == "event_manager")
    bound_accounts = sum(1 for user in users if user.get("player_id") or user.get("linked_player_ids"))
    rows = []
    for user in users:
        username = user["username"]
        display_name = user.get("display_name") or username
        region_name = get_user_region_label(user) or "未设置"
        role = user.get("role") or "member"
        status_value = "active" if user.get("active") else "inactive"
        tags = []
        if username == ADMIN_USERNAME:
            tags.append('<span class="chip">主管理员</span>')
        else:
            tags.append(f'<span class="chip">{escape(account_role_label(user))}</span>')
        if ctx.current_user and username == ctx.current_user["username"]:
            tags.append('<span class="chip">当前账号</span>')
        if user.get("active"):
            tags.append('<span class="chip">启用中</span>')
        else:
            tags.append('<span class="chip">已停用</span>')
        if get_user_manager_scope_keys(user):
            manager_labels = get_manager_scope_labels(user, data)
            if manager_labels:
                tags.append(
                    f'<span class="chip">{escape("；".join(manager_labels[:2]))}</span>'
                )
        permission_labels = get_user_permission_labels(user)
        if permission_labels and not is_admin_user(user):
            tags.append(
                f'<span class="chip">{escape("；".join(permission_labels[:2]))}</span>'
            )

        can_delete = username != ADMIN_USERNAME and not (
            ctx.current_user and username == ctx.current_user["username"]
        )
        edit_button = (
            f'<a class="btn btn-sm btn-outline-dark" href="/accounts?{urlencode({"edit_username": username})}">编辑账号</a>'
        )
        permission_button = (
            f'<a class="btn btn-sm btn-outline-dark" href="/permissions?{urlencode({"username": username})}">权限控制</a>'
        )
        binding_button = (
            f'<a class="btn btn-sm btn-outline-dark" href="/bindings?{urlencode({"username": username})}">绑定参赛ID</a>'
            if is_admin_user(ctx.current_user)
            else ""
        )
        delete_button = (
            f"""
            <form method="post" action="/accounts" class="m-0">
              <input type="hidden" name="action" value="delete">
              <input type="hidden" name="username" value="{escape(username)}">
              <input class="form-control form-control-sm mb-1" name="delete_confirmation" placeholder="输入 {escape(username)} 确认">
              <button type="submit" class="btn btn-sm btn-outline-danger" data-confirm="确认删除账号 {escape(username)}？该账号的登录会话也会失效。">删除账号</button>
            </form>
            """
            if can_delete
            else '<span class="small text-secondary">不可删除</span>'
        )

        rows.append(
            f"""
            <tr data-account-row data-account-keyword="{escape((username + ' ' + display_name + ' ' + region_name).lower())}" data-account-role="{escape(role)}" data-account-status="{status_value}">
              <td>{escape(username)}</td>
              <td>{escape(display_name)}</td>
              <td>{escape(region_name)}</td>
              <td>{''.join(tags)}</td>
              <td><div class="d-flex flex-wrap gap-2">{edit_button}{permission_button}{binding_button}{delete_button}</div></td>
            </tr>
            """
        )

    account_form_title = "编辑账号" if editing_account else "新增账号"
    account_form_copy = (
        "可以在这里调整赛事负责人负责范围、所在地区和登录密码。具体赛事权限请到“权限控制”里按地区系列赛授权。"
        if editing_account
        else "新增后即可使用新账号登录当前网站。"
    )
    username_field_html = (
        f"""
        <input type="hidden" name="editing_username" value="{escape(current_form['editing_username'])}">
        <input class="form-control" name="username" value="{escape(current_form['username'])}" readonly>
        <div class="small text-secondary mt-2">编辑模式下用户名保持不变。</div>
        """
        if editing_account
        else f'<input class="form-control" name="username" value="{escape(current_form["username"])}" placeholder="例如 team_manager">'
    )
    password_help = "留空表示不修改当前密码。" if editing_account else "至少 6 位。"
    submit_action = "update" if editing_account else "create"
    submit_label = "保存账号设置" if editing_account else "创建账号"
    cancel_edit_button = (
        '<a class="btn btn-outline-dark" href="/accounts">取消编辑</a>'
        if editing_account
        else ""
    )
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">身份与权限</div>
      <h1 class="display-6 fw-semibold mb-3">账号管理</h1>
      <p class="mb-0 opacity-75">集中维护后台登录账号、基础身份、地区归属和参赛 ID 绑定入口。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-3">
        <div class="col-6 col-xl-3">
          <div class="stat-card h-100 p-3 border-0">
            <div class="stat-label">账号总数</div>
            <div class="stat-value mt-2">{total_accounts}</div>
          </div>
        </div>
        <div class="col-6 col-xl-3">
          <div class="stat-card h-100 p-3 border-0">
            <div class="stat-label">启用中</div>
            <div class="stat-value mt-2">{active_accounts}</div>
          </div>
        </div>
        <div class="col-6 col-xl-3">
          <div class="stat-card h-100 p-3 border-0">
            <div class="stat-label">赛事负责人</div>
            <div class="stat-value mt-2">{manager_accounts}</div>
          </div>
        </div>
        <div class="col-6 col-xl-3">
          <div class="stat-card h-100 p-3 border-0">
            <div class="stat-label">已绑定参赛</div>
            <div class="stat-value mt-2">{bound_accounts}</div>
          </div>
        </div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">首页赛事动态</h2>
          <p class="section-copy mb-0">默认自动显示最近一个有效比赛日的特殊事件，例如最高分选手、连胜选手、连败选手和阵营走势；管理员也可以手动覆盖。</p>
        </div>
        <span class="chip">{'自动生成' if activity_mode != 'custom' else '手动覆盖'}</span>
      </div>
      <div class="form-panel p-3 p-lg-4">
        <form method="post" action="/accounts">
          <input type="hidden" name="action" value="save_dashboard_activity_settings">
          <div class="row g-3">
            <div class="col-12 col-lg-4">
              <label class="form-label">生成方式</label>
              <select class="form-select" name="activity_mode">
                <option value="auto"{' selected' if activity_mode != 'custom' else ''}>自动生成最近比赛日特殊事件</option>
                <option value="custom"{' selected' if activity_mode == 'custom' else ''}>管理员手动覆盖</option>
              </select>
              <div class="small text-secondary mt-2">自动模式不会显示赛果，只提炼特殊事件。</div>
            </div>
            <div class="col-12 col-lg-8">
              <label class="form-label">手动动态</label>
              <textarea class="form-control" name="activity_custom_text" rows="6" placeholder="标签 | 时间/范围 | 动态正文 | 链接\n例如：最高分选手 | 2026-04-12 | 可杰单日拿到 21 分 | /players/player-player-27">{escape(activity_custom_text)}</textarea>
              <div class="small text-secondary mt-2">每行一条，格式为“标签 | 时间/范围 | 动态正文 | 链接”。选择自动模式时这里会保留但不展示。</div>
            </div>
          </div>
          <div class="d-flex flex-wrap gap-2 mt-4">
            <button type="submit" class="btn btn-dark">保存赛事动态设置</button>
            <a class="btn btn-outline-dark" href="/dashboard">查看首页</a>
          </div>
        </form>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-4">
        <div class="col-12 col-xl-5">
          <div class="form-panel h-100 p-3 p-lg-4">
            <h2 class="section-title mb-2">{account_form_title}</h2>
            <p class="section-copy mb-4">{account_form_copy}</p>
            <form method="post" action="/accounts">
              <input type="hidden" name="action" value="{submit_action}">
              <div class="mb-3">
                <label class="form-label">用户名</label>
                {username_field_html}
              </div>
              <div class="mb-3">
                <label class="form-label">显示名称</label>
                <input class="form-control" name="display_name" value="{escape(current_form['display_name'])}" placeholder="例如 赛事运营">
              </div>
              <div class="mb-3">
                <label class="form-label">账号类型</label>
                <select class="form-select" name="role">
                  {option_tags({k: v for k, v in ACCOUNT_ROLE_OPTIONS.items() if k != 'admin'}, current_form['role'])}
                </select>
                <div class="small text-secondary mt-2">赛事负责人只表示可被授予赛事类权限；真正能管理哪些功能，要到“权限控制”里按地区 + 系列赛单独勾选，可多选。</div>
              </div>
              <div class="mb-3">
                <label class="form-label">赛事负责人管辖范围</label>
                {build_manager_scope_options(ctx.current_user, current_form.get('manager_scope_keys', []))}
                <div class="small text-secondary mt-2">仅当账号类型选择“赛事负责人”时生效，可多选。后续权限控制页会在这个范围内授予赛事权限。</div>
              </div>
              <div class="mb-3">
                <label class="form-label">所在地区</label>
                {legacy.build_region_picker(current_form['province_name'], current_form['region_name'], 'account-create')}
              </div>
              <div class="mb-4">
                <label class="form-label">登录密码</label>
                <input class="form-control" name="password" type="password" autocomplete="new-password">
                <div class="small text-secondary mt-2">{password_help}</div>
              </div>
              <div class="d-flex flex-wrap gap-2">
                <button type="submit" class="btn btn-dark">{submit_label}</button>
                {cancel_edit_button}
              </div>
            </form>
          </div>
        </div>
        <div class="col-12 col-xl-7">
          <div class="panel h-100 shadow-sm p-3 p-lg-4">
            <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
              <div>
                <h2 class="section-title mb-2">现有账号</h2>
                <p class="section-copy mb-0">管理员账号会被保护，当前登录账号也不能在这里直接删除；更细的能力授权请进入“权限控制”。</p>
              </div>
              <div class="d-flex flex-wrap gap-2">
                <a class="btn btn-outline-dark" href="/permissions">打开权限控制页</a>
                <a class="btn btn-outline-dark" href="/audit-logs">查看操作审计</a>
              </div>
            </div>
            <div class="form-panel p-3 mb-3">
              <div class="row g-2 align-items-end">
                <div class="col-12 col-lg-5">
                  <label class="form-label">搜索账号</label>
                  <input class="form-control" id="account-search" placeholder="用户名、显示名或地区">
                </div>
                <div class="col-6 col-lg-3">
                  <label class="form-label">账号类型</label>
                  <select class="form-select" id="account-role-filter">
                    <option value="">全部类型</option>
                    <option value="member">普通成员</option>
                    <option value="event_manager">赛事负责人</option>
                    <option value="admin">管理员</option>
                  </select>
                </div>
                <div class="col-6 col-lg-2">
                  <label class="form-label">状态</label>
                  <select class="form-select" id="account-status-filter">
                    <option value="">全部状态</option>
                    <option value="active">启用中</option>
                    <option value="inactive">已停用</option>
                  </select>
                </div>
                <div class="col-12 col-lg-2">
                  <button class="btn btn-outline-dark w-100" type="button" id="account-filter-reset">重置</button>
                </div>
              </div>
              <div class="small text-secondary mt-2"><span id="account-visible-count">{total_accounts}</span> / {total_accounts} 个账号</div>
            </div>
            <div class="table-responsive">
              <table class="table align-middle">
                <thead>
                  <tr>
                    <th>用户名</th>
                    <th>显示名称</th>
                    <th>地区</th>
                    <th>身份 / 状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(rows)}
                  <tr id="account-empty-row" class="d-none">
                    <td colspan="5" class="text-secondary">没有符合筛选条件的账号。</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3">
        <div>
          <h2 class="section-title mb-2">系统入口</h2>
          <p class="section-copy mb-0">账号页只保留身份相关工作流，其他系统能力进入对应后台模块处理。</p>
        </div>
        <div class="d-flex flex-wrap gap-2">
          <a class="btn btn-outline-dark" href="/ai-admin">AI 管理</a>
          <a class="btn btn-outline-dark" href="/access-stats">访问统计</a>
          <a class="btn btn-outline-dark" href="/audit-logs">操作审计</a>
        </div>
      </div>
    </section>
    <script>
      (function () {{
        const searchInput = document.getElementById("account-search");
        const roleFilter = document.getElementById("account-role-filter");
        const statusFilter = document.getElementById("account-status-filter");
        const resetButton = document.getElementById("account-filter-reset");
        const visibleCount = document.getElementById("account-visible-count");
        const emptyRow = document.getElementById("account-empty-row");
        const rows = Array.from(document.querySelectorAll("[data-account-row]"));

        function applyFilters() {{
          const keyword = (searchInput && searchInput.value || "").trim().toLowerCase();
          const role = roleFilter && roleFilter.value || "";
          const status = statusFilter && statusFilter.value || "";
          let shown = 0;
          rows.forEach((row) => {{
            const matchesKeyword = !keyword || (row.getAttribute("data-account-keyword") || "").includes(keyword);
            const matchesRole = !role || row.getAttribute("data-account-role") === role;
            const matchesStatus = !status || row.getAttribute("data-account-status") === status;
            const visible = matchesKeyword && matchesRole && matchesStatus;
            row.classList.toggle("d-none", !visible);
            if (visible) shown += 1;
          }});
          if (visibleCount) visibleCount.textContent = String(shown);
          if (emptyRow) emptyRow.classList.toggle("d-none", shown !== 0);
        }}

        [searchInput, roleFilter, statusFilter].forEach((control) => {{
          if (control) control.addEventListener("input", applyFilters);
          if (control) control.addEventListener("change", applyFilters);
        }});
        if (resetButton) {{
          resetButton.addEventListener("click", function () {{
            if (searchInput) searchInput.value = "";
            if (roleFilter) roleFilter.value = "";
            if (statusFilter) statusFilter.value = "";
            applyFilters();
          }});
        }}
        document.querySelectorAll("[data-confirm]").forEach((button) => {{
          button.addEventListener("click", function (event) {{
            const message = button.getAttribute("data-confirm") || "确认执行这个操作？";
            if (!window.confirm(message)) event.preventDefault();
          }});
        }});
        applyFilters();
      }})();
    </script>
    """
    return layout("账号管理", body, ctx, alert=alert)


def get_permission_control_page(
    ctx: RequestContext,
    alert: str = "",
    selected_username: str = "",
    form_values: dict[str, Any] | None = None,
) -> str:
    users = load_users()
    requested_username = (
        str(form_values.get("username") or "").strip()
        if form_values
        else selected_username.strip() or form_value(ctx.query, "username").strip()
    )
    target_user = next((user for user in users if user["username"] == requested_username), None)
    if not target_user and users:
        target_user = users[0]
    current_form = {
        "username": target_user["username"] if target_user else "",
        "permission_keys": list(target_user.get("permissions", [])) if target_user else [],
        "manager_scope_keys": list(target_user.get("manager_scope_keys", [])) if target_user else [],
    }
    if form_values:
        current_form.update(
            {
                "username": str(form_values.get("username") or current_form["username"]).strip(),
                "permission_keys": normalize_permission_keys(form_values.get("permission_keys", [])),
                "manager_scope_keys": [
                    str(scope_key or "").strip()
                    for scope_key in form_values.get("manager_scope_keys", [])
                    if str(scope_key or "").strip()
                ],
            }
        )
        target_user = next(
            (user for user in users if user["username"] == current_form["username"]),
            target_user,
        )

    total_accounts = len(users)
    admin_accounts = sum(1 for user in users if is_admin_user(user))
    permissioned_accounts = sum(
        1
        for user in users
        if is_admin_user(user) or normalize_permission_keys(user.get("permissions", []))
    )
    scoped_accounts = sum(1 for user in users if get_user_manager_scope_keys(user))
    user_cards: list[str] = []
    for user in users:
        permission_labels = get_user_permission_labels(user)
        username = user["username"]
        display_name = user.get("display_name") or username
        role = user.get("role") or "member"
        region_label = get_user_region_label(user) or "未设置地区"
        selected_class = " border-primary" if target_user and username == target_user.get("username") else ""
        user_cards.append(
            f"""
            <a class="team-link-card shadow-sm p-3 h-100 d-block{selected_class}" href="/permissions?{urlencode({"username": username})}" data-permission-user data-permission-keyword="{escape((username + ' ' + display_name + ' ' + region_label).lower())}" data-permission-role="{escape(role)}">
              <div class="d-flex justify-content-between align-items-start gap-3">
                <div>
                  <div class="fw-semibold">{escape(display_name)}</div>
                  <div class="small text-secondary mt-1">{escape(username)} · {escape(account_role_label(user))}</div>
                  <div class="small text-secondary mt-1">{escape(region_label)}</div>
                </div>
                <span class="chip">{'管理员' if is_admin_user(user) else f'{len(permission_labels)} 项权限'}</span>
              </div>
            </a>
            """
        )

    permission_panel = '<div class="alert alert-secondary mb-0">请先从左侧选择一个账号。</div>'
    if target_user:
        role_label = account_role_label(target_user)
        selected_permissions = normalize_permission_keys(current_form["permission_keys"])
        selected_event_permissions = [
            key for key in selected_permissions if key in EVENT_SCOPE_PERMISSION_KEYS
        ]
        selected_scope_keys = [
            str(scope_key or "").strip()
            for scope_key in current_form["manager_scope_keys"]
            if str(scope_key or "").strip()
        ]
        permission_summary = "；".join(get_user_permission_labels(target_user)) or "暂未授予额外权限"
        scope_warning = (
            '<div class="alert alert-warning mb-4">已勾选赛事类权限，请至少选择一个“地区 + 系列赛”负责范围后再保存。</div>'
            if selected_event_permissions and not selected_scope_keys
            else ""
        )
        if is_admin_user(target_user):
            permission_panel = f"""
            <section class="panel shadow-sm p-3 p-lg-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 mb-4">
                <div>
                  <h2 class="section-title mb-2">管理员权限</h2>
                  <p class="section-copy mb-0">当前账号默认拥有全部后台能力，不通过权限表单单独配置。</p>
                </div>
                <a class="btn btn-outline-dark" href="/accounts?{urlencode({'edit_username': target_user['username']})}">编辑账号资料</a>
              </div>
              <div class="row g-3">
                <div class="col-12 col-md-6"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">账号</div><div class="stat-value mt-2">{escape(target_user['username'])}</div></div></div>
                <div class="col-12 col-md-6"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">身份</div><div class="stat-value mt-2">{escape(role_label)}</div></div></div>
              </div>
              <div class="alert alert-light mt-4 mb-0">管理员自动具备：{escape('；'.join(PERMISSION_LABELS[key] for key in get_all_permission_keys()))}</div>
            </section>
            """
        else:
            permission_panel = f"""
            <section class="form-panel shadow-sm p-3 p-lg-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 mb-4">
                <div>
                  <h2 class="section-title mb-2">编辑账号权限</h2>
                  <p class="section-copy mb-0">先授予功能权限，再限定赛事类权限的生效范围。组织类和数据类权限不受赛事范围限制。</p>
                </div>
                <div class="d-flex flex-wrap gap-2 align-items-start">
                  <a class="btn btn-outline-dark" href="/accounts?{urlencode({'edit_username': target_user['username']})}">编辑账号资料</a>
                  <a class="btn btn-outline-dark" href="/audit-logs">查看审计</a>
                </div>
              </div>
              <div class="row g-3 mb-4">
                <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 border-0"><div class="stat-label">功能权限</div><div class="stat-value mt-2">{len(selected_permissions)}</div></div></div>
                <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 border-0"><div class="stat-label">赛事权限</div><div class="stat-value mt-2">{len(selected_event_permissions)}</div></div></div>
                <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 border-0"><div class="stat-label">负责范围</div><div class="stat-value mt-2">{len(selected_scope_keys)}</div></div></div>
                <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 border-0"><div class="stat-label">账号身份</div><div class="stat-value mt-2">{escape(role_label)}</div></div></div>
              </div>
              <div class="alert alert-light mb-4">当前权限：{escape(permission_summary)}</div>
              {scope_warning}
              <form method="post" action="/permissions">
                <input type="hidden" name="username" value="{escape(current_form['username'])}">
                <div class="panel shadow-sm p-3 p-lg-4 mb-4">
                  <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 mb-3">
                    <div>
                      <h3 class="h5 mb-1">功能权限</h3>
                      <p class="small text-secondary mb-0">勾选账号可以进入和维护的后台能力。</p>
                    </div>
                    <span class="chip">{len(selected_permissions)} / {len(PERMISSION_LABELS)} 已选</span>
                  </div>
                  {legacy.build_permission_options(current_form['permission_keys'])}
                </div>
                <div class="panel shadow-sm p-3 p-lg-4 mb-4">
                  <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 mb-3">
                    <div>
                      <h3 class="h5 mb-1">赛事负责范围</h3>
                      <p class="small text-secondary mb-0">范围口径为“地区 + 系列赛”。赛事类权限只会在这些已选范围内生效。</p>
                    </div>
                    <span class="chip">{len(selected_scope_keys)} 个范围</span>
                  </div>
                  {build_manager_scope_options(ctx.current_user, current_form['manager_scope_keys'])}
                </div>
                <div class="d-flex flex-wrap gap-2">
                  <button type="submit" class="btn btn-dark">保存权限设置</button>
                  <a class="btn btn-outline-dark" href="/permissions?{urlencode({'username': target_user['username']})}">重置表单</a>
                </div>
              </form>
            </section>
            """

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">RBAC</div>
      <h1 class="display-6 fw-semibold mb-3">用户权限控制</h1>
      <p class="mb-0 opacity-75">集中控制账号的门派、战队、赛事与数据维护权限。赛事类权限必须绑定负责范围。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-3">
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 border-0"><div class="stat-label">账号总数</div><div class="stat-value mt-2">{total_accounts}</div></div></div>
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 border-0"><div class="stat-label">管理员</div><div class="stat-value mt-2">{admin_accounts}</div></div></div>
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 border-0"><div class="stat-label">已授权账号</div><div class="stat-value mt-2">{permissioned_accounts}</div></div></div>
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 border-0"><div class="stat-label">有赛事范围</div><div class="stat-value mt-2">{scoped_accounts}</div></div></div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="row g-4">
        <div class="col-12 col-xl-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">账号目录</h2>
              <p class="section-copy mb-0">选择一个账号后，在右侧维护权限。</p>
            </div>
            <a class="btn btn-outline-dark" href="/accounts">账号管理</a>
          </div>
          <div class="form-panel p-3 mb-3">
            <label class="form-label">搜索账号</label>
            <input class="form-control mb-2" id="permission-user-search" placeholder="用户名、显示名或地区">
            <label class="form-label">账号类型</label>
            <select class="form-select" id="permission-role-filter">
              <option value="">全部类型</option>
              <option value="member">普通成员</option>
              <option value="event_manager">赛事负责人</option>
              <option value="admin">管理员</option>
            </select>
            <div class="small text-secondary mt-2"><span id="permission-user-visible-count">{total_accounts}</span> / {total_accounts} 个账号</div>
          </div>
          <div class="row g-3" id="permission-user-list">
            {''.join(f'<div class="col-12" data-permission-user-shell>{card}</div>' for card in user_cards)}
            <div class="col-12 d-none" id="permission-user-empty">
              <div class="alert alert-secondary mb-0">没有符合筛选条件的账号。</div>
            </div>
          </div>
        </div>
        <div class="col-12 col-xl-8">
          {permission_panel}
        </div>
      </div>
    </section>
    <script>
      (function () {{
        const searchInput = document.getElementById("permission-user-search");
        const roleFilter = document.getElementById("permission-role-filter");
        const visibleCount = document.getElementById("permission-user-visible-count");
        const emptyState = document.getElementById("permission-user-empty");
        const shells = Array.from(document.querySelectorAll("[data-permission-user-shell]"));

        function applyUserFilters() {{
          const keyword = (searchInput && searchInput.value || "").trim().toLowerCase();
          const role = roleFilter && roleFilter.value || "";
          let shown = 0;
          shells.forEach((shell) => {{
            const card = shell.querySelector("[data-permission-user]");
            const matchesKeyword = !keyword || (card && (card.getAttribute("data-permission-keyword") || "").includes(keyword));
            const matchesRole = !role || (card && card.getAttribute("data-permission-role") === role);
            const visible = matchesKeyword && matchesRole;
            shell.classList.toggle("d-none", !visible);
            if (visible) shown += 1;
          }});
          if (visibleCount) visibleCount.textContent = String(shown);
          if (emptyState) emptyState.classList.toggle("d-none", shown !== 0);
        }}

        [searchInput, roleFilter].forEach((control) => {{
          if (control) control.addEventListener("input", applyUserFilters);
          if (control) control.addEventListener("change", applyUserFilters);
        }});
        applyUserFilters();
      }})();
    </script>
    """
    return layout("权限控制", body, ctx, alert=alert)


def handle_accounts(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_accounts_page(ctx))

    action = form_value(ctx.form, "action")
    users = load_users()

    if action in {"save_ai_daily_brief_settings", "save_ai_prompt_templates"}:
        return start_response_html(
            start_response,
            "200 OK",
            get_accounts_page(ctx, alert="AI 配置已移至独立的 AI 管理页。"),
        )

    if action == "save_dashboard_activity_settings":
        activity_mode = form_value(ctx.form, "activity_mode", "auto").strip()
        custom_text = form_value(ctx.form, "activity_custom_text")
        custom_items: list[dict[str, str]] = []
        for raw_line in custom_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = [part.strip() for part in line.split("|")]
            if len(parts) < 3:
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_accounts_page(
                        ctx,
                        alert="手动动态每行至少需要包含：标签 | 时间/范围 | 动态正文。",
                        form_values={
                            "activity_mode": activity_mode,
                            "activity_custom_text": custom_text,
                        },
                    ),
                )
            custom_items.append(
                {
                    "label": parts[0] or "手动动态",
                    "time_label": parts[1] or "管理员编辑",
                    "text": parts[2],
                    "href": parts[3] if len(parts) >= 4 and parts[3] else "/competitions",
                }
            )
        if activity_mode == "custom" and not custom_items:
            return start_response_html(
                start_response,
                "200 OK",
                get_accounts_page(
                    ctx,
                    alert="选择手动覆盖时，请至少填写一条动态。",
                    form_values={
                        "activity_mode": activity_mode,
                        "activity_custom_text": custom_text,
                    },
                ),
            )
        save_dashboard_activity_settings(activity_mode, custom_items)
        return start_response_html(
            start_response,
            "200 OK",
            get_accounts_page(ctx, alert="首页赛事动态设置已保存。"),
        )

    if action == "create":
        username = form_value(ctx.form, "username").strip()
        display_name = form_value(ctx.form, "display_name").strip()
        role = form_value(ctx.form, "role", "member").strip()
        province_name = form_value(ctx.form, "province_name", DEFAULT_PROVINCE_NAME).strip()
        region_name = form_value(ctx.form, "region_name", "广州市").strip()
        manager_scope_keys = [
            str(item or "").strip()
            for item in ctx.form.get("manager_scope_key", [])
            if str(item or "").strip()
        ]
        password = form_value(ctx.form, "password")
        error = validate_account_form(
            username,
            display_name,
            password,
            users,
            role,
            province_name,
            region_name,
            manager_scope_keys=manager_scope_keys,
        )
        if error:
            return start_response_html(
                start_response,
                "200 OK",
                get_accounts_page(
                    ctx,
                    alert=error,
                    form_values={
                        "username": username,
                        "display_name": display_name,
                        "role": role,
                        "province_name": province_name or DEFAULT_PROVINCE_NAME,
                        "region_name": region_name or "广州市",
                        "manager_scope_keys": manager_scope_keys,
                    },
                ),
            )

        password_salt, password_hash = hash_password(password)
        normalized_province, normalized_region = normalize_user_location(
            province_name,
            region_name,
        )
        users.append(
            {
                "username": username,
                "display_name": display_name,
                "password_salt": password_salt,
                "password_hash": password_hash,
                "active": True,
                "player_id": None,
                "linked_player_ids": [],
                "manager_scope_keys": manager_scope_keys if role == "event_manager" else [],
                "permissions": [],
                "role": role,
                "province_name": normalized_province or DEFAULT_PROVINCE_NAME,
                "region_name": normalized_region or "广州市",
            }
        )
        save_users(users)
        audit_action(
            ctx,
            "account.create",
            target_type="user",
            target_id=username,
            summary=f"创建账号 {username}",
            metadata={"role": role, "region_name": normalized_region or "广州市"},
        )
        return start_response_html(
            start_response,
            "200 OK",
            get_accounts_page(ctx, alert=f"账号 {username} 已创建。"),
        )

    if action == "update":
        editing_username = form_value(ctx.form, "editing_username").strip()
        display_name = form_value(ctx.form, "display_name").strip()
        role = form_value(ctx.form, "role", "member").strip()
        province_name = form_value(ctx.form, "province_name", DEFAULT_PROVINCE_NAME).strip()
        region_name = form_value(ctx.form, "region_name", "广州市").strip()
        manager_scope_keys = [
            str(item or "").strip()
            for item in ctx.form.get("manager_scope_key", [])
            if str(item or "").strip()
        ]
        password = form_value(ctx.form, "password")
        existing_user = next((user for user in users if user["username"] == editing_username), None)
        if not existing_user:
            return start_response_html(
                start_response,
                "200 OK",
                get_accounts_page(ctx, alert="没有找到要编辑的账号。"),
            )
        if editing_username == ADMIN_USERNAME and role != "admin":
            role = "admin"
        error = validate_account_update_form(
            display_name,
            password,
            role,
            province_name,
            region_name,
            manager_scope_keys=manager_scope_keys,
        )
        if error:
            return start_response_html(
                start_response,
                "200 OK",
                get_accounts_page(
                    ctx,
                    alert=error,
                    form_values={
                        "editing_username": editing_username,
                        "username": editing_username,
                        "display_name": display_name,
                        "role": role,
                        "province_name": province_name or DEFAULT_PROVINCE_NAME,
                        "region_name": region_name or "广州市",
                        "manager_scope_keys": manager_scope_keys,
                    },
                ),
            )
        normalized_province, normalized_region = normalize_user_location(
            province_name,
            region_name,
        )
        updated_users = []
        for user in users:
            if user["username"] != editing_username:
                updated_users.append(user)
                continue
            updated_user = {
                **user,
                "display_name": display_name,
                "role": role,
                "manager_scope_keys": (
                    manager_scope_keys
                    if role == "event_manager"
                    else list(user.get("manager_scope_keys", []))
                ),
                "permissions": (
                    normalize_permission_keys(user.get("permissions", []))
                    if role == "event_manager"
                    else [key for key in normalize_permission_keys(user.get("permissions", [])) if key not in legacy.EVENT_SCOPE_PERMISSION_KEYS]
                ),
                "province_name": normalized_province or DEFAULT_PROVINCE_NAME,
                "region_name": normalized_region or "广州市",
            }
            if password:
                password_salt, password_hash = hash_password(password)
                updated_user["password_salt"] = password_salt
                updated_user["password_hash"] = password_hash
            updated_users.append(updated_user)
        save_users(updated_users)
        audit_action(
            ctx,
            "account.update",
            target_type="user",
            target_id=editing_username,
            summary=f"更新账号 {editing_username}",
            metadata={
                "role": role,
                "region_name": normalized_region or "广州市",
                "password_changed": bool(password),
            },
        )
        return start_response_html(
            start_response,
            "200 OK",
            get_accounts_page(ctx, alert=f"账号 {editing_username} 已更新。"),
        )

    if action == "delete":
        username = form_value(ctx.form, "username").strip()
        if not username:
            return start_response_html(
                start_response,
                "200 OK",
                get_accounts_page(ctx, alert="缺少要删除的账号。"),
            )
        if username == ADMIN_USERNAME:
            return start_response_html(
                start_response,
                "200 OK",
                get_accounts_page(ctx, alert="主管理员账号不能删除。"),
            )
        if ctx.current_user and username == ctx.current_user["username"]:
            return start_response_html(
                start_response,
                "200 OK",
                get_accounts_page(ctx, alert="当前登录账号不能删除。"),
            )
        if not any(user["username"] == username for user in users):
            return start_response_html(
                start_response,
                "200 OK",
                get_accounts_page(ctx, alert="没有找到要删除的账号。"),
            )
        if form_value(ctx.form, "delete_confirmation").strip() != username:
            return start_response_html(
                start_response,
                "200 OK",
                get_accounts_page(ctx, alert=f"删除账号前，请在确认框输入完整用户名：{username}。"),
            )

        users = [user for user in users if user["username"] != username]
        revoke_user_sessions(username)
        save_users(users)
        audit_action(
            ctx,
            "account.delete",
            target_type="user",
            target_id=username,
            summary=f"删除账号 {username}",
        )
        return start_response_html(
            start_response,
            "200 OK",
            get_accounts_page(ctx, alert=f"账号 {username} 已删除。"),
        )

    return start_response_html(
        start_response,
        "200 OK",
        get_accounts_page(ctx, alert="未识别的操作。"),
    )



def handle_permission_control(ctx: RequestContext, start_response):
    guard = require_admin(ctx, start_response)
    if guard is not None:
        return guard

    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_permission_control_page(ctx))

    users = load_users()
    username = form_value(ctx.form, "username").strip()
    permission_keys = [
        str(permission_key or "").strip()
        for permission_key in ctx.form.get("permission_key", [])
        if str(permission_key or "").strip()
    ]
    manager_scope_keys = [
        str(scope_key or "").strip()
        for scope_key in ctx.form.get("manager_scope_key", [])
        if str(scope_key or "").strip()
    ]
    target_user = next((user for user in users if user["username"] == username), None)
    if not target_user:
        return start_response_html(
            start_response,
            "200 OK",
            get_permission_control_page(ctx, alert="没有找到要设置权限的账号。"),
        )
    if is_admin_user(target_user):
        return start_response_html(
            start_response,
            "200 OK",
            get_permission_control_page(
                ctx,
                alert="管理员默认拥有全部权限，无需单独配置。",
                selected_username=username,
            ),
        )

    error = validate_permission_assignment(permission_keys, manager_scope_keys)
    if error:
        return start_response_html(
            start_response,
            "200 OK",
            get_permission_control_page(
                ctx,
                alert=error,
                selected_username=username,
                form_values={
                    "username": username,
                    "permission_keys": permission_keys,
                    "manager_scope_keys": manager_scope_keys,
                },
            ),
        )

    updated_users = []
    for user in users:
        if user["username"] != username:
            updated_users.append(user)
            continue
        updated_users.append(
            {
                **user,
                "permissions": normalize_permission_keys(permission_keys),
                "manager_scope_keys": manager_scope_keys,
            }
        )
    save_users(updated_users)
    audit_action(
        ctx,
        "permission.update",
        target_type="user",
        target_id=username,
        summary=f"更新账号 {username} 的权限",
        metadata={
            "permission_keys": normalize_permission_keys(permission_keys),
            "manager_scope_keys": manager_scope_keys,
        },
    )
    return start_response_html(
        start_response,
        "200 OK",
        get_permission_control_page(
            ctx,
            alert=f"账号 {username} 的权限已更新。",
            selected_username=username,
        ),
    )
