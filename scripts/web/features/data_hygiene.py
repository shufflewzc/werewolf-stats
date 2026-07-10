from __future__ import annotations

from copy import deepcopy
from html import escape
from typing import Any

import web_app as legacy

RequestContext = legacy.RequestContext
append_alert_query = legacy.append_alert_query
audit_action = legacy.audit_action
form_value = legacy.form_value
get_user_bound_player_ids = legacy.get_user_bound_player_ids
layout = legacy.layout
load_users = legacy.load_users
load_validated_data = legacy.load_validated_data
redirect = legacy.redirect
save_repository_state = legacy.save_repository_state
start_response_html = legacy.start_response_html


def _appearance_count(data: dict[str, Any], player_id: str) -> int:
    return sum(
        1
        for match in data.get("matches", [])
        for entry in match.get("players", [])
        if str(entry.get("player_id") or "").strip() == player_id
    )


def _bound_count(users: list[dict[str, Any]], player_id: str) -> int:
    return sum(1 for user in users if player_id in get_user_bound_player_ids(user))


def _replace_user_player_id(user: dict[str, Any], source_id: str, target_id: str) -> None:
    if str(user.get("player_id") or "").strip() == source_id:
        user["player_id"] = target_id
    linked = [str(item or "").strip() for item in user.get("linked_player_ids", [])]
    if source_id in linked:
        linked = [target_id if item == source_id else item for item in linked]
        user["linked_player_ids"] = list(dict.fromkeys(item for item in linked if item))
    bound_players = user.get("bound_players")
    if isinstance(bound_players, list):
        for item in bound_players:
            if isinstance(item, dict) and str(item.get("player_id") or "").strip() == source_id:
                item["player_id"] = target_id


def _merge_player(data: dict[str, Any], users: list[dict[str, Any]], source_id: str, target_id: str) -> int:
    source = next((item for item in data["players"] if item.get("player_id") == source_id), None)
    target = next((item for item in data["players"] if item.get("player_id") == target_id), None)
    if not source or not target:
        raise ValueError("源档案或目标档案不存在。")
    moved_appearances = 0
    for match in data.get("matches", []):
        for entry in match.get("players", []):
            if str(entry.get("player_id") or "").strip() != source_id:
                continue
            entry["player_id"] = target_id
            entry["player_name"] = str(target.get("display_name") or target_id)
            moved_appearances += 1
        for key in ("mvp_player_id", "svp_player_id", "scapegoat_player_id"):
            if str(match.get(key) or "").strip() == source_id:
                match[key] = target_id
    for team in data.get("teams", []):
        members = [target_id if str(item or "").strip() == source_id else str(item or "").strip() for item in team.get("members", [])]
        team["members"] = list(dict.fromkeys(item for item in members if item))
        if str(team.get("captain_player_id") or "").strip() == source_id:
            team["captain_player_id"] = target_id
    for row in data.get("season_player_dimension_stats", []):
        if str(row.get("player_id") or "").strip() == source_id:
            row["player_id"] = target_id
    for user in users:
        _replace_user_player_id(user, source_id, target_id)
    data["players"] = [item for item in data["players"] if item.get("player_id") != source_id]
    return moved_appearances


def get_data_hygiene_page(ctx: RequestContext, alert: str = "") -> str:
    data = load_validated_data()
    users = load_users()
    players = list(data.get("players", []))
    player_by_id = {str(item.get("player_id") or ""): item for item in players}
    rows = []
    for player in players:
        player_id = str(player.get("player_id") or "").strip()
        appearances = _appearance_count(data, player_id)
        bindings = _bound_count(users, player_id)
        auto_created = "自动创建" in str(player.get("notes") or "")
        if appearances or bindings or not auto_created:
            continue
        team = next((item for item in data.get("teams", []) if item.get("team_id") == player.get("team_id")), {})
        rows.append(
            f"<tr><td>{escape(player.get('display_name') or player_id)}</td><td><code>{escape(player_id)}</code></td>"
            f"<td>{escape(team.get('name') or '未归属战队')}</td><td><span class=\"chip\">无出场</span></td>"
            f"<td><form method=\"post\" action=\"/data-hygiene\" class=\"d-flex gap-2\"><input type=\"hidden\" name=\"action\" value=\"delete_empty\"><input type=\"hidden\" name=\"player_id\" value=\"{escape(player_id)}\"><input class=\"form-control form-control-sm\" name=\"confirmation\" placeholder=\"输入 {escape(player_id)} 确认\"><button class=\"btn btn-sm btn-outline-danger\" type=\"submit\">删除</button></form></td></tr>"
        )
    options = "".join(
        f'<option value="{escape(player_id)}">{escape(player.get("display_name") or player_id)} · {escape(player_id)} · 出场 {_appearance_count(data, player_id)} 局</option>'
        for player_id, player in sorted(player_by_id.items(), key=lambda item: (str(item[1].get("display_name") or ""), item[0]))
        if player_id
    )
    body = f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h1 class="section-title mb-2">档案清理与合并</h1>
      <p class="section-copy mb-0">合并会把源档案的比赛记录、奖项、阵容、维度数据和账号绑定迁移到目标档案；完成后源档案会被删除。请先确认两者是同一位选手。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h2 class="section-title mb-3">合并重复选手档案</h2>
      <form method="post" action="/data-hygiene" class="row g-3 align-items-end">
        <input type="hidden" name="action" value="merge_players">
        <div class="col-12 col-lg-4"><label class="form-label">源档案（会删除）</label><select class="form-select" name="source_player_id">{options}</select></div>
        <div class="col-12 col-lg-4"><label class="form-label">目标档案（保留）</label><select class="form-select" name="target_player_id">{options}</select></div>
        <div class="col-12 col-lg-4"><label class="form-label">确认</label><input class="form-control" name="confirmation" placeholder="输入 合并 确认"><button class="btn btn-dark mt-2" type="submit">执行合并</button></div>
      </form>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex justify-content-between align-items-end gap-3 mb-3"><div><h2 class="section-title mb-2">可安全删除的自动档案</h2><p class="section-copy mb-0">仅显示自动创建、没有出场记录、且没有账号绑定的选手。</p></div><span class="chip">{len(rows)} 个</span></div>
      <div class="table-responsive"><table class="table align-middle"><thead><tr><th>名称</th><th>档案 ID</th><th>战队</th><th>状态</th><th>操作</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="5" class="text-secondary">暂无可安全删除的自动档案。</td></tr>'}</tbody></table></div>
    </section>
    """
    return layout("档案清理与合并", body, ctx, alert=alert)


def handle_data_hygiene(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_data_hygiene_page(ctx))
    action = form_value(ctx.form, "action").strip()
    data = load_validated_data()
    users = load_users()
    if action == "delete_empty":
        player_id = form_value(ctx.form, "player_id").strip()
        if form_value(ctx.form, "confirmation").strip() != player_id:
            return redirect(start_response, append_alert_query("/data-hygiene", "请完整输入档案 ID 后再删除。"))
        player = next((item for item in data.get("players", []) if item.get("player_id") == player_id), None)
        if not player or _appearance_count(data, player_id) or _bound_count(users, player_id) or "自动创建" not in str(player.get("notes") or ""):
            return redirect(start_response, append_alert_query("/data-hygiene", "该档案不符合安全删除条件。"))
        for team in data.get("teams", []):
            team["members"] = [item for item in team.get("members", []) if item != player_id]
        data["players"] = [item for item in data["players"] if item.get("player_id") != player_id]
        errors = save_repository_state(data, users)
        if errors:
            return redirect(start_response, append_alert_query("/data-hygiene", "删除失败：" + "；".join(errors[:2])))
        audit_action(
            ctx,
            "data_hygiene.delete_empty_player",
            target_type="player",
            target_id=player_id,
            summary=f"删除无出场自动档案 {player_id}",
        )
        return redirect(start_response, append_alert_query("/data-hygiene", "已删除无出场自动档案。"))
    if action == "merge_players":
        source_id = form_value(ctx.form, "source_player_id").strip()
        target_id = form_value(ctx.form, "target_player_id").strip()
        if form_value(ctx.form, "confirmation").strip() != "合并" or not source_id or source_id == target_id:
            return redirect(start_response, append_alert_query("/data-hygiene", "请选定不同档案，并输入“合并”确认。"))
        try:
            next_data = deepcopy(data)
            next_users = deepcopy(users)
            moved = _merge_player(next_data, next_users, source_id, target_id)
            errors = save_repository_state(next_data, next_users)
            if errors:
                raise ValueError("；".join(errors[:2]))
        except ValueError as exc:
            return redirect(start_response, append_alert_query("/data-hygiene", f"合并失败：{exc}"))
        audit_action(
            ctx,
            "data_hygiene.merge_players",
            target_type="player",
            target_id=target_id,
            summary=f"合并选手档案 {source_id} 到 {target_id}",
            metadata={"source_player_id": source_id, "moved_appearances": moved},
        )
        return redirect(start_response, append_alert_query("/data-hygiene", f"合并完成，已迁移 {moved} 条出场记录。"))
    return redirect(start_response, append_alert_query("/data-hygiene", "未知操作。"))
