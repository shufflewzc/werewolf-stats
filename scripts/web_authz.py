from __future__ import annotations

from typing import Any


ADMIN_USERNAME = "admin"
PERMISSION_GROUPS = [
    {
        "title": "赛事权限",
        "copy": "这些权限仍然会受“地区 + 系列赛”范围限制，勾选后还需要给账号分配负责范围。",
        "keys": [
            "competition_catalog_manage",
            "competition_season_manage",
            "match_manage",
        ],
    },
    {
        "title": "组织权限",
        "copy": "用于门派和战队日常管理，管理员始终拥有全部权限。",
        "keys": [
            "guild_manage",
            "guild_honor_manage",
            "team_manage",
        ],
    },
    {
        "title": "数据权限",
        "copy": "用于帮助选手绑定赛季参赛 ID 等数据维护操作。",
        "keys": [
            "player_binding_manage",
        ],
    },
]
PERMISSION_LABELS = {
    "competition_catalog_manage": "编辑赛事页信息",
    "competition_season_manage": "管理赛季档期",
    "match_manage": "录入和编辑比赛",
    "guild_manage": "门派管理",
    "guild_honor_manage": "维护门派历届荣誉",
    "team_manage": "战队管理",
    "player_binding_manage": "参赛 ID 绑定管理",
}
PERMISSION_DESCRIPTIONS = {
    "competition_catalog_manage": "可编辑地区系列赛的赛事页标题、专题说明、专题页展示内容。",
    "competition_season_manage": "可创建、编辑、改名和删除对应地区系列赛下的赛季。",
    "match_manage": "可为对应地区系列赛录入、编辑比赛结果与比赛详情。",
    "guild_manage": "可创建门派，并对所有门派执行管理操作。",
    "guild_honor_manage": "可手动编辑所有门派的历届荣誉展示内容。",
    "team_manage": "可管理战队图标、战队资料，以及战队中心内的管理操作。",
    "player_binding_manage": "可帮助选手绑定赛季参赛 ID，并整理历史赛事数据。",
}
EVENT_SCOPE_PERMISSION_KEYS = {
    "competition_catalog_manage",
    "competition_season_manage",
    "match_manage",
}
SERIES_MANAGEMENT_PERMISSION_KEYS = {
    "competition_catalog_manage",
    "competition_season_manage",
}
DEFAULT_EVENT_MANAGER_PERMISSION_KEYS = [
    "competition_catalog_manage",
    "competition_season_manage",
    "match_manage",
    "player_binding_manage",
]

# Series-level permissions are deliberately separate from ``permissions_json``.
# The latter remains the source of truth for platform-wide organisation/data
# permissions while these keys are stored in ``user_scope_grants``.
SCOPE_PERMISSION_LABELS = {
    "competition_catalog_manage": "编辑赛事页",
    "competition_season_manage": "管理赛季档期",
    "match_schedule_manage": "创建赛程",
    "match_result_manage": "编辑比赛结果",
    "match_import_manage": "上传比赛数据",
    "dimension_data_manage": "管理维度数据",
    "season_asset_manage": "上传赛季素材",
    "prediction_manage": "管理胜率预测",
    "scope_audit_view": "查看赛区审计",
}
SCOPE_PERMISSION_DESCRIPTIONS = {
    "competition_catalog_manage": "编辑当前地区系列赛的赛事页信息。",
    "competition_season_manage": "创建、编辑和维护当前系列赛的赛季档期。",
    "match_schedule_manage": "创建单场赛程或批量创建待补录比赛。",
    "match_result_manage": "录入和修改已有比赛的结果与详情。",
    "match_import_manage": "预检、确认和查看当前系列赛的比赛数据导入。",
    "dimension_data_manage": "上传、修改和查看当前系列赛的维度数据。",
    "season_asset_manage": "上传当前系列赛的战队图标和选手头像等赛季素材。",
    "prediction_manage": "创建、编辑、发布和重新模拟当前系列赛的胜率预测。",
    "scope_audit_view": "查看当前系列赛的导入记录和审计日志。",
}
SCOPE_PERMISSION_KEYS = tuple(SCOPE_PERMISSION_LABELS)

LEGACY_SCOPE_PERMISSION_EXPANSIONS = {
    "competition_catalog_manage": ("competition_catalog_manage",),
    "competition_season_manage": ("competition_season_manage",),
    "match_manage": (
        "match_schedule_manage",
        "match_result_manage",
        "match_import_manage",
        "dimension_data_manage",
        "season_asset_manage",
        "prediction_manage",
        "scope_audit_view",
    ),
}

SCOPE_PERMISSION_PRESETS = {
    "scope_admin": {
        "label": "赛事负责人（全权限）",
        "permission_keys": list(SCOPE_PERMISSION_KEYS),
        "is_scope_admin": True,
    },
    "event_editor": {
        "label": "赛事编辑",
        "permission_keys": [
            "match_schedule_manage",
            "match_result_manage",
            "prediction_manage",
        ],
        "is_scope_admin": False,
    },
    "data_uploader": {
        "label": "数据上传员",
        "permission_keys": [
            "match_import_manage",
            "dimension_data_manage",
            "season_asset_manage",
        ],
        "is_scope_admin": False,
    },
    "content_operator": {
        "label": "赛事内容运营",
        "permission_keys": [
            "competition_catalog_manage",
            "competition_season_manage",
        ],
        "is_scope_admin": False,
    },
    "audit_viewer": {
        "label": "只读审计",
        "permission_keys": ["scope_audit_view"],
        "is_scope_admin": False,
    },
}


def is_admin_user(user: dict[str, Any] | None) -> bool:
    return bool(
        user
        and (
            user.get("username") == ADMIN_USERNAME
            or user.get("role") == "admin"
        )
    )


def is_event_manager_user(user: dict[str, Any] | None) -> bool:
    return bool(user and user.get("role") == "event_manager")


def get_all_permission_keys() -> list[str]:
    return list(PERMISSION_LABELS.keys())


def normalize_permission_keys(values: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    known_permissions = set(get_all_permission_keys())
    normalized_keys: list[str] = []
    for value in values or []:
        normalized = str(value or "").strip()
        if normalized and normalized in known_permissions and normalized not in normalized_keys:
            normalized_keys.append(normalized)
    return normalized_keys


def get_user_permission_keys(user: dict[str, Any] | None) -> list[str]:
    if is_admin_user(user):
        return get_all_permission_keys()
    if not user:
        return []
    return normalize_permission_keys(user.get("permissions", []))


def user_has_permission(user: dict[str, Any] | None, permission_key: str) -> bool:
    return is_admin_user(user) or permission_key in get_user_permission_keys(user)


def user_has_any_permission(
    user: dict[str, Any] | None,
    permission_keys: list[str] | tuple[str, ...] | set[str],
) -> bool:
    if is_admin_user(user):
        return True
    granted_permissions = set(get_user_permission_keys(user))
    return any(permission_key in granted_permissions for permission_key in permission_keys)


def get_user_permission_labels(user: dict[str, Any] | None) -> list[str]:
    return [
        PERMISSION_LABELS[permission_key]
        for permission_key in get_user_permission_keys(user)
        if permission_key in PERMISSION_LABELS
    ]


def build_manager_scope_key(region_name: str, series_slug: str) -> str:
    return f"{region_name.strip()}::{series_slug.strip()}"


def normalize_scope_key(value: Any) -> str:
    normalized = str(value or "").strip()
    region_name, separator, series_slug = normalized.partition("::")
    if not separator or not region_name.strip() or not series_slug.strip():
        return ""
    return build_manager_scope_key(region_name, series_slug)


def get_user_manager_scope_keys(user: dict[str, Any] | None) -> list[str]:
    if not user:
        return []
    ordered_keys: list[str] = []
    for value in user.get("manager_scope_keys", []) or []:
        normalized = str(value or "").strip()
        if normalized and normalized not in ordered_keys:
            ordered_keys.append(normalized)
    return ordered_keys


def get_all_scope_permission_keys() -> list[str]:
    return list(SCOPE_PERMISSION_KEYS)


def normalize_scope_permission_keys(
    values: list[str] | tuple[str, ...] | set[str] | None,
) -> list[str]:
    known_permissions = set(SCOPE_PERMISSION_KEYS)
    normalized_keys: list[str] = []
    for value in values or []:
        normalized = str(value or "").strip()
        if normalized and normalized in known_permissions and normalized not in normalized_keys:
            normalized_keys.append(normalized)
    return normalized_keys


def expand_legacy_scope_permission_keys(
    values: list[str] | tuple[str, ...] | set[str] | None,
) -> list[str]:
    expanded: list[str] = []
    for value in values or []:
        normalized = str(value or "").strip()
        candidates = LEGACY_SCOPE_PERMISSION_EXPANSIONS.get(normalized, (normalized,))
        for candidate in candidates:
            if candidate in SCOPE_PERMISSION_KEYS and candidate not in expanded:
                expanded.append(candidate)
    return expanded


def build_legacy_scope_grants(user: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not user:
        return []
    permissions = expand_legacy_scope_permission_keys(user.get("permissions", []))
    if not permissions:
        return []
    return [
        {
            "scope_key": scope_key,
            "permissions": list(permissions),
            "is_scope_admin": False,
            "created_at": "",
            "updated_at": "",
            "updated_by_username": "",
            "legacy_fallback": True,
        }
        for raw_scope_key in get_user_manager_scope_keys(user)
        if (scope_key := normalize_scope_key(raw_scope_key))
    ]


def normalize_scope_grants(
    grants: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> list[dict[str, Any]]:
    grants_by_scope: dict[str, dict[str, Any]] = {}
    for grant in grants or []:
        if not isinstance(grant, dict):
            continue
        scope_key = normalize_scope_key(grant.get("scope_key"))
        if not scope_key:
            continue
        raw_scope_admin = grant.get("is_scope_admin", False)
        is_scope_admin = bool(
            raw_scope_admin is True
            or (type(raw_scope_admin) is int and raw_scope_admin == 1)
        )
        grants_by_scope[scope_key] = {
            "scope_key": scope_key,
            "permissions": normalize_scope_permission_keys(grant.get("permissions", [])),
            "is_scope_admin": is_scope_admin,
            "created_at": str(grant.get("created_at") or ""),
            "updated_at": str(grant.get("updated_at") or ""),
            "updated_by_username": str(grant.get("updated_by_username") or "").strip(),
            **(
                {"legacy_fallback": True}
                if grant.get("legacy_fallback")
                else {}
            ),
        }
    return [grants_by_scope[scope_key] for scope_key in sorted(grants_by_scope)]


def get_user_scope_grants(user: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not user:
        return []
    explicit_grants = normalize_scope_grants(user.get("scope_grants", []))
    if user.get("scope_grants_authoritative"):
        return explicit_grants
    grants_by_scope = {grant["scope_key"]: grant for grant in explicit_grants}
    # Legacy fallback is per scope. An explicit empty grant therefore remains a
    # deliberate revocation instead of being silently repopulated.
    for legacy_grant in build_legacy_scope_grants(user):
        grants_by_scope.setdefault(legacy_grant["scope_key"], legacy_grant)
    return [grants_by_scope[scope_key] for scope_key in sorted(grants_by_scope)]


def get_user_scope_keys(user: dict[str, Any] | None) -> list[str]:
    return [grant["scope_key"] for grant in get_user_scope_grants(user)]


def get_user_scope_grant(
    user: dict[str, Any] | None,
    scope_key: str,
) -> dict[str, Any] | None:
    normalized_scope_key = normalize_scope_key(scope_key)
    if not normalized_scope_key:
        return None
    return next(
        (
            grant
            for grant in get_user_scope_grants(user)
            if grant["scope_key"] == normalized_scope_key
        ),
        None,
    )


def user_is_scope_admin(user: dict[str, Any] | None, scope_key: str) -> bool:
    if is_admin_user(user):
        return True
    if not is_event_manager_user(user):
        return False
    grant = get_user_scope_grant(user, scope_key)
    return bool(grant and grant.get("is_scope_admin"))


def user_has_scope_permission(
    user: dict[str, Any] | None,
    scope_key: str,
    permission_key: str,
) -> bool:
    if is_admin_user(user):
        return True
    if not is_event_manager_user(user):
        return False
    normalized_permission = str(permission_key or "").strip()
    if normalized_permission not in SCOPE_PERMISSION_KEYS:
        return False
    grant = get_user_scope_grant(user, scope_key)
    return bool(
        grant
        and (
            grant.get("is_scope_admin")
            or normalized_permission in grant.get("permissions", [])
        )
    )


def user_has_any_scope_permission(
    user: dict[str, Any] | None,
    scope_key: str,
    permission_keys: list[str] | tuple[str, ...] | set[str],
) -> bool:
    return any(
        user_has_scope_permission(user, scope_key, permission_key)
        for permission_key in permission_keys
    )


def get_scope_permission_preset(preset_key: str) -> list[str]:
    preset = SCOPE_PERMISSION_PRESETS.get(str(preset_key or "").strip())
    if not preset:
        return []
    return list(preset["permission_keys"])


def user_can_assign_scope_grant(
    actor: dict[str, Any] | None,
    scope_key: str,
    permission_keys: list[str] | tuple[str, ...] | set[str],
    *,
    is_scope_admin: bool = False,
) -> bool:
    normalized_permissions = normalize_scope_permission_keys(permission_keys)
    if len(normalized_permissions) != len(
        {
            str(permission_key or "").strip()
            for permission_key in permission_keys
            if str(permission_key or "").strip()
        }
    ):
        return False
    if is_admin_user(actor):
        return True
    if is_scope_admin or not user_is_scope_admin(actor, scope_key):
        return False
    return all(
        user_has_scope_permission(actor, scope_key, permission_key)
        for permission_key in normalized_permissions
    )


def user_can_manage_scoped_user_lifecycle(
    actor: dict[str, Any] | None,
    target_user: dict[str, Any] | None,
) -> bool:
    if is_admin_user(actor):
        return bool(target_user)
    if not actor or not target_user or is_admin_user(target_user):
        return False
    actor_username = str(actor.get("username") or "").strip()
    if not actor_username or actor_username == str(target_user.get("username") or "").strip():
        return False
    if str(target_user.get("created_by_username") or "").strip() != actor_username:
        return False
    if any(grant.get("is_scope_admin") for grant in get_user_scope_grants(target_user)):
        return False
    target_scope_keys = get_user_scope_keys(target_user)
    return bool(target_scope_keys) and all(
        user_is_scope_admin(actor, scope_key) for scope_key in target_scope_keys
    )
