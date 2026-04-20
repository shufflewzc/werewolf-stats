from __future__ import annotations

import secrets
from typing import Any

import web_app as legacy

RequestContext = legacy.RequestContext
SESSION_COOKIE = legacy.SESSION_COOKIE
SESSION_COOKIE_MAX_AGE_SECONDS = legacy.SESSION_COOKIE_MAX_AGE_SECONDS
can_manage_matches = legacy.can_manage_matches
form_value = legacy.form_value
get_team_captain_id = legacy.get_team_captain_id
get_team_scope = legacy.get_team_scope
get_user_bound_player_ids = legacy.get_user_bound_player_ids
get_user_by_player_id = legacy.get_user_by_player_id
is_admin_user = legacy.is_admin_user
layout = legacy.layout
load_membership_requests = legacy.load_membership_requests
redirect = legacy.redirect
remove_user_player_binding = legacy.remove_user_player_binding
revoke_user_sessions = legacy.revoke_user_sessions
save_repository_state = legacy.save_repository_state
save_session = legacy.save_session
set_user_primary_player_id = legacy.set_user_primary_player_id
start_response_html = legacy.start_response_html
user_has_match_history = legacy.user_has_match_history
user_has_permission = legacy.user_has_permission


def collect_team_stage_groups_from_form(form: dict[str, list[str]]) -> list[dict[str, str]]:
    stage_groups: list[dict[str, str]] = []
    for stage_key in legacy.STAGE_OPTIONS:
        group_label = form_value(form, f"stage_group_{stage_key}").strip()
        if not group_label:
            continue
        stage_groups.append({"stage": stage_key, "group_label": group_label})
    return stage_groups


def get_team_member_removal_error(
    data: dict[str, Any],
    team: dict[str, Any] | None,
    acting_player: dict[str, Any] | None,
    member_player_id: str,
) -> str:
    if not team or not acting_player or not member_player_id:
        return "没有找到要处理的队员。"
    if member_player_id not in team.get("members", []):
        return "该队员已经不在当前战队中。"
    if get_team_captain_id(team) == member_player_id:
        return "当前认领负责人不能被直接移除。"
    if member_player_id == acting_player["player_id"]:
        return "你不能删除自己。"
    if user_has_match_history(data, member_player_id):
        return "该队员已经有历史比赛记录，不能直接删除。"
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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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


def issue_fresh_team_center_session(start_response, username: str):
    revoke_user_sessions(username)
    token = secrets.token_urlsafe(24)
    save_session(token, username)
    return redirect(
        start_response,
        "/team-center",
        headers=[
            (
                "Set-Cookie",
                f"{SESSION_COOKIE}={token}; Path=/; Max-Age={SESSION_COOKIE_MAX_AGE_SECONDS}; HttpOnly; SameSite=Lax",
            )
        ],
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


def is_unclaimed_team(team: dict[str, Any] | None) -> bool:
    if not team:
        return False
    return not str(team.get("captain_player_id") or "").strip()


def get_team_center_page(
    ctx: RequestContext,
    alert: str = "",
    join_values: dict[str, str] | None = None,
) -> str:
    from web.features.team_center_v2 import get_team_center_page_impl

    return get_team_center_page_impl(ctx, alert, join_values)


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
            get_team_center_page(ctx, alert="切换当前主身份失败：" + "；".join(errors[:3])),
        )
    return issue_fresh_team_center_session(start_response, username)


def handle_team_center(ctx: RequestContext, start_response):
    from web.features.team_center_v2 import handle_team_center_impl

    return handle_team_center_impl(ctx, start_response)
