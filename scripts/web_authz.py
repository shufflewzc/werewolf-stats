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


def get_user_manager_scope_keys(user: dict[str, Any] | None) -> list[str]:
    if not user:
        return []
    ordered_keys: list[str] = []
    for value in user.get("manager_scope_keys", []) or []:
        normalized = str(value or "").strip()
        if normalized and normalized not in ordered_keys:
            ordered_keys.append(normalized)
    return ordered_keys
