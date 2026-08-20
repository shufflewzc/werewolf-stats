from __future__ import annotations

import json
import re
from html import escape
from typing import Any
from urllib.parse import urlencode

import web_app as legacy
from web_authz import (
    SCOPE_PERMISSION_KEYS,
    SCOPE_PERMISSION_LABELS,
    SCOPE_PERMISSION_PRESETS,
    get_scope_permission_preset,
    get_user_scope_grants,
    is_admin_user,
    normalize_scope_key,
    user_can_assign_scope_grant,
    user_can_manage_scoped_user_lifecycle,
    user_is_scope_admin,
)


RequestContext = legacy.RequestContext
RepositoryConflictError = legacy.RepositoryConflictError
audit_action = legacy.audit_action
build_scope_grants_etag = legacy.build_scope_grants_etag
build_user_authorization_etag = legacy.build_user_authorization_etag
form_value = legacy.form_value
hash_password = legacy.hash_password
layout = legacy.layout
load_users = legacy.load_users
revoke_user_sessions = legacy.revoke_user_sessions
save_users = legacy.save_users
start_response_html = legacy.start_response_html


def _catalog_scope_options() -> list[dict[str, str]]:
    data = legacy.load_validated_data()
    entries = legacy.load_series_catalog(data)
    options_by_key: dict[str, dict[str, str]] = {}
    for entry in entries:
        region_name = str(entry.get("region_name") or "").strip()
        series_slug = str(entry.get("series_slug") or "").strip()
        scope_key = normalize_scope_key(f"{region_name}::{series_slug}")
        if not scope_key:
            continue
        series_name = str(
            entry.get("series_name") or entry.get("competition_name") or series_slug
        ).strip()
        competition_name = str(entry.get("competition_name") or "").strip()
        options_by_key[scope_key] = {
            "scope_key": scope_key,
            "label": f"{region_name} · {series_name}",
            "competition_name": competition_name,
        }
    return [options_by_key[key] for key in sorted(options_by_key)]


def _available_scope_options(
    actor: dict[str, Any] | None,
) -> list[dict[str, str]]:
    options = _catalog_scope_options()
    if is_admin_user(actor):
        return options
    return [
        option
        for option in options
        if user_is_scope_admin(actor, option["scope_key"])
    ]


def _can_access_scope_accounts(actor: dict[str, Any] | None) -> bool:
    return bool(is_admin_user(actor) or _available_scope_options(actor))


def _can_manage_target(
    actor: dict[str, Any] | None,
    target_user: dict[str, Any] | None,
) -> bool:
    return bool(
        target_user
        and target_user.get("role") == "event_manager"
        and user_can_manage_scoped_user_lifecycle(actor, target_user)
    )


def _form_values(ctx: RequestContext, key: str) -> list[str]:
    return [str(value or "").strip() for value in ctx.form.get(key, [])]


def _decode_permission_value(value: str) -> tuple[str, str]:
    try:
        payload = json.loads(str(value or ""))
    except (TypeError, json.JSONDecodeError):
        return "", ""
    if not isinstance(payload, dict):
        return "", ""
    return (
        normalize_scope_key(payload.get("scope_key")),
        str(payload.get("permission_key") or "").strip(),
    )


def build_requested_scope_grants(
    ctx: RequestContext,
    actor: dict[str, Any] | None,
    known_scope_keys: set[str],
) -> tuple[list[dict[str, Any]] | None, str]:
    requested_scope_keys: list[str] = []
    for raw_scope_key in _form_values(ctx, "scope_key"):
        scope_key = normalize_scope_key(raw_scope_key)
        if not scope_key or scope_key not in known_scope_keys:
            return None, "所选赛区不存在或不在当前账号可管理范围内。"
        if scope_key not in requested_scope_keys:
            requested_scope_keys.append(scope_key)
    if not requested_scope_keys:
        return None, "请至少选择一个地区系列赛。"

    preset_key = form_value(ctx.form, "preset", "custom").strip() or "custom"
    if preset_key != "custom" and preset_key not in SCOPE_PERMISSION_PRESETS:
        return None, "权限预设无效，请刷新页面后重试。"

    custom_permissions_by_scope: dict[str, list[str]] = {
        scope_key: [] for scope_key in requested_scope_keys
    }
    if preset_key == "custom":
        for encoded_permission in _form_values(ctx, "scope_permission"):
            scope_key, permission_key = _decode_permission_value(encoded_permission)
            if (
                scope_key not in custom_permissions_by_scope
                or permission_key not in SCOPE_PERMISSION_KEYS
            ):
                return None, "自定义权限中包含无效赛区或权限项。"
            if permission_key not in custom_permissions_by_scope[scope_key]:
                custom_permissions_by_scope[scope_key].append(permission_key)

    requested_admin_scope_keys = {
        normalize_scope_key(value)
        for value in _form_values(ctx, "scope_admin_key")
        if normalize_scope_key(value)
    }
    if not requested_admin_scope_keys.issubset(set(requested_scope_keys)):
        return None, "赛事负责人范围必须同时出现在所选地区系列赛中。"
    if preset_key == "scope_admin":
        requested_admin_scope_keys = set(requested_scope_keys)

    preset_permissions = (
        get_scope_permission_preset(preset_key) if preset_key != "custom" else []
    )
    grants: list[dict[str, Any]] = []
    for scope_key in requested_scope_keys:
        permissions = (
            list(preset_permissions)
            if preset_key != "custom"
            else custom_permissions_by_scope[scope_key]
        )
        is_scope_admin = scope_key in requested_admin_scope_keys
        if not user_can_assign_scope_grant(
            actor,
            scope_key,
            permissions,
            is_scope_admin=is_scope_admin,
        ):
            return None, f"当前账号不能授予 {scope_key} 的所选权限。"
        grants.append(
            {
                "scope_key": scope_key,
                "permissions": permissions,
                "is_scope_admin": is_scope_admin,
            }
        )
    return grants, ""


def _managed_users(
    actor: dict[str, Any] | None,
    users: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if is_admin_user(actor):
        return [user for user in users if user.get("role") == "event_manager"]
    return [user for user in users if _can_manage_target(actor, user)]


def _grant_summary(grant: dict[str, Any], scope_labels: dict[str, str]) -> str:
    scope_key = str(grant.get("scope_key") or "")
    label = scope_labels.get(scope_key, scope_key)
    if grant.get("is_scope_admin"):
        return f"{label}：赛事负责人（全权限）"
    permission_labels = [
        SCOPE_PERMISSION_LABELS[key]
        for key in grant.get("permissions", [])
        if key in SCOPE_PERMISSION_LABELS
    ]
    return f"{label}：{'、'.join(permission_labels) if permission_labels else '无操作权限'}"


def _permission_value(scope_key: str, permission_key: str) -> str:
    return json.dumps(
        {"scope_key": scope_key, "permission_key": permission_key},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _scope_grant_fields(
    actor: dict[str, Any] | None,
    scope_options: list[dict[str, str]],
    selected_grants: list[dict[str, Any]],
) -> str:
    selected_by_scope = {
        str(grant.get("scope_key") or ""): grant for grant in selected_grants
    }
    cards: list[str] = []
    for option in scope_options:
        scope_key = option["scope_key"]
        selected_grant = selected_by_scope.get(scope_key, {})
        selected_permissions = set(selected_grant.get("permissions", []))
        selected = " checked" if scope_key in selected_by_scope else ""
        permission_controls = []
        for permission_key, label in SCOPE_PERMISSION_LABELS.items():
            checked = " checked" if permission_key in selected_permissions else ""
            permission_controls.append(
                f"""
                <label class="form-check small me-3 mb-2">
                  <input class="form-check-input" type="checkbox" name="scope_permission" value="{escape(_permission_value(scope_key, permission_key))}"{checked}>
                  <span class="form-check-label">{escape(label)}</span>
                </label>
                """
            )
        scope_admin_control = ""
        if is_admin_user(actor):
            admin_checked = " checked" if selected_grant.get("is_scope_admin") else ""
            scope_admin_control = f"""
            <label class="form-check mt-2">
              <input class="form-check-input" type="checkbox" name="scope_admin_key" value="{escape(scope_key)}"{admin_checked}>
              <span class="form-check-label">设为该系列赛的赛事负责人（可维护全部赛季数据）</span>
            </label>
            """
        cards.append(
            f"""
            <div class="border rounded p-3 mb-3">
              <label class="form-check fw-semibold">
                <input class="form-check-input" type="checkbox" name="scope_key" value="{escape(scope_key)}"{selected}>
                <span class="form-check-label">{escape(option['label'])}</span>
              </label>
              <div class="d-flex flex-wrap mt-3">{''.join(permission_controls)}</div>
              {scope_admin_control}
            </div>
            """
        )
    return "".join(cards) or '<div class="alert alert-warning mb-0">当前账号没有可分配的地区系列赛。</div>'


def get_scope_accounts_page(
    ctx: RequestContext,
    *,
    alert: str = "",
    editing_username: str = "",
) -> str:
    actor = ctx.current_user
    users = load_users()
    scope_options = _available_scope_options(actor)
    scope_labels = {option["scope_key"]: option["label"] for option in _catalog_scope_options()}
    visible_users = _managed_users(actor, users)
    editing_user = next(
        (user for user in visible_users if user["username"] == editing_username),
        None,
    )
    selected_grants = get_user_scope_grants(editing_user) if editing_user else []
    grants_etag = build_scope_grants_etag(selected_grants) if editing_user else ""
    preset_options = ['<option value="custom">自定义权限</option>']
    for preset_key, preset in SCOPE_PERMISSION_PRESETS.items():
        if preset.get("is_scope_admin") and not is_admin_user(actor):
            continue
        preset_options.append(
            f'<option value="{escape(preset_key)}">{escape(str(preset["label"]))}</option>'
        )

    rows: list[str] = []
    for user in visible_users:
        username = str(user.get("username") or "")
        grant_lines = "<br>".join(
            escape(_grant_summary(grant, scope_labels))
            for grant in get_user_scope_grants(user)
        ) or "未分配"
        next_active = "0" if user.get("active") else "1"
        status_label = "停用" if user.get("active") else "启用"
        rows.append(
            f"""
            <tr>
              <td><strong>{escape(username)}</strong><br><span class="small text-secondary">{escape(str(user.get('display_name') or username))}</span></td>
              <td>{'启用中' if user.get('active') else '已停用'}</td>
              <td class="small">{grant_lines}</td>
              <td>
                <div class="d-flex flex-wrap gap-2">
                  <a class="btn btn-sm btn-outline-dark" href="/console/accounts?{urlencode({'edit_username': username})}">编辑权限</a>
                  <form method="post" action="/console/accounts" class="m-0">
                    <input type="hidden" name="action" value="set_active">
                    <input type="hidden" name="username" value="{escape(username)}">
                    <input type="hidden" name="active" value="{next_active}">
                    <input type="hidden" name="user_authorization_etag" value="{build_user_authorization_etag(user)}">
                    <button class="btn btn-sm btn-outline-dark" type="submit">{status_label}</button>
                  </form>
                </div>
                <form method="post" action="/console/accounts" class="d-flex gap-2 mt-2">
                  <input type="hidden" name="action" value="reset_password">
                  <input type="hidden" name="username" value="{escape(username)}">
                  <input type="hidden" name="user_authorization_etag" value="{build_user_authorization_etag(user)}">
                  <input class="form-control form-control-sm" type="password" name="password" minlength="6" placeholder="新密码（至少 6 位）" required>
                  <button class="btn btn-sm btn-outline-dark text-nowrap" type="submit">重置密码</button>
                </form>
              </td>
            </tr>
            """
        )

    editing = bool(editing_user)
    form_title = f"编辑 {editing_user['username']}" if editing else "创建赛区运营账号"
    body = f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between gap-3">
        <div>
          <div class="eyebrow mb-2">账号与审计</div>
          <h1 class="section-title mb-2">分赛区账号</h1>
          <p class="section-copy mb-0">按地区系列赛分配后台操作；赛事负责人可维护授权系列赛内全部赛季的选手、战队、比赛、上传和预测数据，并只能管理本人创建且未共享到其他赛区的子账号。</p>
        </div>
        <a class="btn btn-outline-dark align-self-start" href="/console">返回控制台</a>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h2 class="h5 mb-3">{escape(form_title)}</h2>
      <form method="post" action="/console/accounts">
        <input type="hidden" name="action" value="{'save_grants' if editing else 'create'}">
        {f'<input type="hidden" name="username" value="{escape(editing_user["username"])}">' if editing else ''}
        {f'<input type="hidden" name="grants_etag" value="{escape(grants_etag)}">' if editing else ''}
        <div class="row g-3 mb-3">
          <div class="col-12 col-md-4">
            <label class="form-label">用户名</label>
            <input class="form-control" name="username" value="{escape(str(editing_user.get('username') or '')) if editing else ''}"{' readonly' if editing else ''} required>
          </div>
          <div class="col-12 col-md-4">
            <label class="form-label">显示名称</label>
            <input class="form-control" name="display_name" value="{escape(str(editing_user.get('display_name') or '')) if editing else ''}" required>
          </div>
          <div class="col-12 col-md-4">
            <label class="form-label">权限预设</label>
            <select class="form-select" name="preset">{''.join(preset_options)}</select>
          </div>
          {'' if editing else '<div class="col-12 col-md-4"><label class="form-label">初始密码</label><input class="form-control" type="password" name="password" minlength="6" required></div>'}
        </div>
        <p class="small text-secondary">选择预设时，以预设权限覆盖下方自定义勾选；需要逐项设置时选择“自定义权限”。</p>
        {_scope_grant_fields(actor, scope_options, selected_grants)}
        <div class="d-flex gap-2 mt-3">
          <button class="btn btn-dark" type="submit">{'保存账号权限' if editing else '创建账号'}</button>
          {('<a class="btn btn-outline-dark" href="/console/accounts">取消编辑</a>' if editing else '')}
        </div>
      </form>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex justify-content-between align-items-center mb-3">
        <h2 class="h5 mb-0">可管理账号</h2>
        <span class="chip">{len(visible_users)} 个</span>
      </div>
      <div class="table-responsive">
        <table class="table align-middle mb-0">
          <thead><tr><th>账号</th><th>状态</th><th>授权范围</th><th>操作</th></tr></thead>
          <tbody>{''.join(rows) if rows else '<tr><td colspan="4" class="text-secondary">暂无可管理的赛区运营账号。</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    """
    return layout("分赛区账号", body, ctx, alert=alert)


def _response(
    ctx: RequestContext,
    start_response,
    status: str,
    message: str,
    *,
    editing_username: str = "",
):
    return start_response_html(
        start_response,
        status,
        get_scope_accounts_page(
            ctx,
            alert=message,
            editing_username=editing_username,
        ),
        ctx=ctx,
    )


def _updated_users(
    users: list[dict[str, Any]],
    username: str,
    updates: dict[str, Any],
) -> list[dict[str, Any]]:
    return [({**user, **updates} if user["username"] == username else user) for user in users]


def handle_scope_accounts_route(ctx: RequestContext, start_response):
    actor = ctx.current_user
    if not _can_access_scope_accounts(actor):
        return _response(ctx, start_response, "403 Forbidden", "当前账号没有分赛区账号管理权限。")

    if ctx.method == "GET":
        editing_username = (
            form_value(ctx.query, "edit_username").strip()
            or form_value(ctx.query, "username").strip()
        )
        return _response(
            ctx,
            start_response,
            "200 OK",
            "",
            editing_username=editing_username,
        )

    users = load_users()
    action = form_value(ctx.form, "action").strip()
    known_scope_keys = {
        option["scope_key"] for option in _available_scope_options(actor)
    }

    if action == "create":
        username = form_value(ctx.form, "username").strip()
        display_name = form_value(ctx.form, "display_name").strip()
        password = form_value(ctx.form, "password")
        if not legacy.USERNAME_PATTERN.match(username):
            return _response(ctx, start_response, "400 Bad Request", "用户名格式无效。")
        if any(user["username"] == username for user in users):
            return _response(ctx, start_response, "409 Conflict", "该用户名已经存在。")
        if not display_name:
            return _response(ctx, start_response, "400 Bad Request", "显示名称不能为空。")
        if len(password) < 6:
            return _response(ctx, start_response, "400 Bad Request", "密码至少需要 6 位。")
        grants, error = build_requested_scope_grants(
            ctx, actor, known_scope_keys
        )
        if error or grants is None:
            return _response(ctx, start_response, "403 Forbidden", error)
        password_salt, password_hash = hash_password(password)
        actor_username = str(actor.get("username") or "")
        actor_authorization_etag = build_user_authorization_etag(actor)
        users.append(
            {
                "username": username,
                "display_name": display_name,
                "password_salt": password_salt,
                "password_hash": password_hash,
                "active": True,
                "player_id": None,
                "linked_player_ids": [],
                "manager_scope_keys": [grant["scope_key"] for grant in grants],
                "scope_grants": grants,
                "scope_grants_authoritative": True,
                "scope_grants_updated_by_username": actor_username,
                "permissions": [],
                "role": "event_manager",
                "created_by_username": actor_username,
                "authorization_actor_username": actor_username,
                "authorization_actor_etag": actor_authorization_etag,
                "province_name": str(actor.get("province_name") or ""),
                "region_name": str(actor.get("region_name") or ""),
                "account_create": True,
            }
        )
        try:
            save_users(users)
        except RepositoryConflictError as exc:
            return _response(
                ctx,
                start_response,
                "409 Conflict",
                str(exc),
            )
        audit_action(
            ctx,
            "scope_account.create",
            target_type="user",
            target_id=username,
            summary=f"创建赛区运营账号 {username}",
            metadata={"scope_grants": grants},
        )
        return _response(ctx, start_response, "200 OK", f"账号 {username} 已创建。")

    username = form_value(ctx.form, "username").strip()
    target_user = next((user for user in users if user["username"] == username), None)
    if not _can_manage_target(actor, target_user):
        return _response(ctx, start_response, "403 Forbidden", "当前账号不能管理该运营账号。")

    if action == "save_grants":
        display_name = form_value(ctx.form, "display_name").strip()
        expected_grants_etag = form_value(ctx.form, "grants_etag").strip()
        if not display_name:
            return _response(
                ctx,
                start_response,
                "400 Bad Request",
                "显示名称不能为空。",
                editing_username=username,
            )
        grants, error = build_requested_scope_grants(
            ctx, actor, known_scope_keys
        )
        if error or grants is None:
            return _response(
                ctx,
                start_response,
                "403 Forbidden",
                error,
                editing_username=username,
            )
        if not re.fullmatch(r"[0-9a-f]{64}", expected_grants_etag):
            return _response(
                ctx,
                start_response,
                "409 Conflict",
                "权限编辑页已过期，请刷新后重试。",
                editing_username=username,
            )
        actor_username = str(actor.get("username") or "")
        actor_authorization_etag = build_user_authorization_etag(actor)
        try:
            save_users(
                _updated_users(
                    users,
                    username,
                    {
                        "display_name": display_name,
                        "user_profile_write": True,
                        "manager_scope_keys": [grant["scope_key"] for grant in grants],
                        "scope_grants": grants,
                        "scope_grants_authoritative": True,
                        "scope_grants_updated_by_username": actor_username,
                        "scope_grants_expected_etag": expected_grants_etag,
                        "expected_user_authorization_etag": build_user_authorization_etag(
                            target_user
                        ),
                        "authorization_actor_username": actor_username,
                        "authorization_actor_etag": actor_authorization_etag,
                    },
                )
            )
        except RepositoryConflictError:
            return _response(
                ctx,
                start_response,
                "409 Conflict",
                "账号权限已被其他管理员更新，请刷新后重新编辑。",
                editing_username=username,
            )
        audit_action(
            ctx,
            "scope_account.permissions.update",
            target_type="user",
            target_id=username,
            summary=f"更新赛区运营账号 {username} 的权限",
            metadata={"scope_grants": grants},
        )
        return _response(ctx, start_response, "200 OK", f"账号 {username} 的权限已更新。")

    if action == "reset_password":
        expected_user_authorization_etag = form_value(
            ctx.form, "user_authorization_etag"
        ).strip()
        if (
            not re.fullmatch(r"[0-9a-f]{64}", expected_user_authorization_etag)
            or build_user_authorization_etag(target_user)
            != expected_user_authorization_etag
        ):
            return _response(
                ctx,
                start_response,
                "409 Conflict",
                "账号状态或权限已发生变化，请刷新后重试。",
            )
        password = form_value(ctx.form, "password")
        if len(password) < 6:
            return _response(ctx, start_response, "400 Bad Request", "密码至少需要 6 位。")
        password_salt, password_hash = hash_password(password)
        try:
            save_users(
                _updated_users(
                    users,
                    username,
                    {
                        "password_salt": password_salt,
                        "password_hash": password_hash,
                        "account_password_write": True,
                        "authorization_actor_username": str(actor.get("username") or ""),
                        "authorization_actor_etag": build_user_authorization_etag(actor),
                        "expected_user_authorization_etag": expected_user_authorization_etag,
                    },
                )
            )
        except RepositoryConflictError as exc:
            return _response(ctx, start_response, "409 Conflict", str(exc))
        revoke_user_sessions(username)
        audit_action(
            ctx,
            "scope_account.password.reset",
            target_type="user",
            target_id=username,
            summary=f"重置赛区运营账号 {username} 的密码",
        )
        return _response(ctx, start_response, "200 OK", f"账号 {username} 的密码已重置。")

    if action == "set_active":
        expected_user_authorization_etag = form_value(
            ctx.form, "user_authorization_etag"
        ).strip()
        if (
            not re.fullmatch(r"[0-9a-f]{64}", expected_user_authorization_etag)
            or build_user_authorization_etag(target_user)
            != expected_user_authorization_etag
        ):
            return _response(
                ctx,
                start_response,
                "409 Conflict",
                "账号状态或权限已发生变化，请刷新后重试。",
            )
        active_value = form_value(ctx.form, "active").strip()
        if active_value not in {"0", "1"}:
            return _response(ctx, start_response, "400 Bad Request", "账号状态无效。")
        active = active_value == "1"
        try:
            save_users(
                _updated_users(
                    users,
                    username,
                    {
                        "active": active,
                        "account_active_write": True,
                        "authorization_actor_username": str(actor.get("username") or ""),
                        "authorization_actor_etag": build_user_authorization_etag(actor),
                        "expected_user_authorization_etag": expected_user_authorization_etag,
                    },
                )
            )
        except RepositoryConflictError as exc:
            return _response(ctx, start_response, "409 Conflict", str(exc))
        if not active:
            revoke_user_sessions(username)
        audit_action(
            ctx,
            "scope_account.status.update",
            target_type="user",
            target_id=username,
            summary=f"{'启用' if active else '停用'}赛区运营账号 {username}",
            metadata={"active": active},
        )
        return _response(
            ctx,
            start_response,
            "200 OK",
            f"账号 {username} 已{'启用' if active else '停用'}。",
        )

    return _response(ctx, start_response, "400 Bad Request", "未识别的账号操作。")
