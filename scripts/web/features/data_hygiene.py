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

SeasonScope = tuple[str, str]
DEFAULT_PLAYER_PHOTO = "assets/players/default-player.svg"


def _normalized_player_photo(player: dict[str, Any]) -> str:
    return str(player.get("photo") or DEFAULT_PLAYER_PHOTO).strip() or DEFAULT_PLAYER_PHOTO


def _preserve_player_photo(source: dict[str, Any], target: dict[str, Any]) -> None:
    source_photo = _normalized_player_photo(source)
    target_photo = _normalized_player_photo(target)
    if source_photo == DEFAULT_PLAYER_PHOTO:
        return
    if target_photo == DEFAULT_PLAYER_PHOTO:
        target["photo"] = source_photo
        return
    if source_photo != target_photo:
        raise ValueError("源档案和目标档案都有不同的自定义头像，请先明确保留哪一个头像。")


def _team_season_scope(team: dict[str, Any] | None) -> SeasonScope | None:
    if not team:
        return None
    competition_name = str(team.get("competition_name") or "").strip()
    season_name = str(team.get("season_name") or "").strip()
    if not competition_name or not season_name:
        return None
    return competition_name, season_name


def _player_season_scope_map(data: dict[str, Any]) -> dict[str, set[SeasonScope]]:
    scopes = {
        str(player.get("player_id") or "").strip(): set()
        for player in data.get("players", [])
        if str(player.get("player_id") or "").strip()
    }
    team_by_id = {
        str(team.get("team_id") or "").strip(): team
        for team in data.get("teams", [])
        if str(team.get("team_id") or "").strip()
    }
    for player in data.get("players", []):
        player_id = str(player.get("player_id") or "").strip()
        scope = _team_season_scope(team_by_id.get(str(player.get("team_id") or "").strip()))
        if player_id and scope:
            scopes.setdefault(player_id, set()).add(scope)
    for team in data.get("teams", []):
        scope = _team_season_scope(team)
        if not scope:
            continue
        related_ids = list(team.get("members", []))
        related_ids.append(team.get("captain_player_id"))
        for value in related_ids:
            player_id = str(value or "").strip()
            if player_id in scopes:
                scopes[player_id].add(scope)
    for match in data.get("matches", []):
        competition_name = str(match.get("competition_name") or "").strip()
        season_name = str(match.get("season") or "").strip()
        if not competition_name or not season_name:
            continue
        scope = (competition_name, season_name)
        for entry in match.get("players", []):
            player_id = str(entry.get("player_id") or "").strip()
            if player_id in scopes:
                scopes[player_id].add(scope)
    for row in data.get("season_player_dimension_stats", []):
        player_id = str(row.get("player_id") or "").strip()
        competition_name = str(row.get("competition_name") or "").strip()
        season_name = str(row.get("season_name") or "").strip()
        if player_id in scopes and competition_name and season_name:
            scopes[player_id].add((competition_name, season_name))
    return scopes


def _case_insensitive_duplicate_groups(
    players: list[dict[str, Any]],
    player_scopes: dict[str, set[SeasonScope]],
) -> list[tuple[SeasonScope, list[dict[str, Any]]]]:
    grouped: dict[tuple[SeasonScope, str], list[dict[str, Any]]] = {}
    for player in players:
        player_id = str(player.get("player_id") or "").strip()
        display_name = str(player.get("display_name") or "").strip()
        scopes = player_scopes.get(player_id, set())
        if not display_name or len(scopes) != 1:
            continue
        scope = next(iter(scopes))
        grouped.setdefault((scope, display_name.casefold()), []).append(player)
    duplicates = [
        (scope, rows)
        for (scope, _normalized_name), rows in grouped.items()
        if len(rows) > 1
    ]
    return sorted(
        duplicates,
        key=lambda item: (
            item[0][0],
            item[0][1],
            str(item[1][0].get("display_name") or "").casefold(),
        ),
    )


def _appearance_count(data: dict[str, Any], player_id: str) -> int:
    return sum(
        1
        for match in data.get("matches", [])
        for entry in match.get("players", [])
        if str(entry.get("player_id") or "").strip() == player_id
    )


def _bound_count(users: list[dict[str, Any]], player_id: str) -> int:
    return sum(1 for user in users if player_id in get_user_bound_player_ids(user))


def _is_auto_created_player(player: dict[str, Any] | None) -> bool:
    if not player:
        return False
    profile_status = str(player.get("profile_status") or "").strip()
    created_source = str(player.get("created_source") or "").strip()
    if profile_status == "auto_created" or created_source in {
        "match_entry",
        "excel_import",
    }:
        return True
    return "自动创建" in str(player.get("notes") or "")


def _delete_player_impact(
    data: dict[str, Any],
    users: list[dict[str, Any]],
    player_id: str,
) -> dict[str, Any]:
    captain_team_ids = [
        str(team.get("team_id") or "").strip()
        for team in data.get("teams", [])
        if str(team.get("captain_player_id") or "").strip() == player_id
    ]
    roster_team_ids = [
        str(team.get("team_id") or "").strip()
        for team in data.get("teams", [])
        if player_id
        in {
            str(member_id or "").strip()
            for member_id in team.get("members", [])
        }
    ]
    dimension_rows = sum(
        1
        for row in data.get("season_player_dimension_stats", [])
        if str(row.get("player_id") or "").strip() == player_id
    )
    award_references = sum(
        1
        for match in data.get("matches", [])
        for field_name in ("mvp_player_id", "svp_player_id", "scapegoat_player_id")
        if str(match.get(field_name) or "").strip() == player_id
    )
    return {
        "appearances": _appearance_count(data, player_id),
        "bindings": _bound_count(users, player_id),
        "captain_team_ids": captain_team_ids,
        "roster_team_ids": roster_team_ids,
        "dimension_rows": dimension_rows,
        "award_references": award_references,
    }


def _delete_empty_player(
    data: dict[str, Any],
    users: list[dict[str, Any]],
    player_id: str,
) -> dict[str, Any]:
    player = next(
        (
            item
            for item in data.get("players", [])
            if str(item.get("player_id") or "").strip() == player_id
        ),
        None,
    )
    if not player or not _is_auto_created_player(player):
        raise ValueError("该档案不是系统自动创建的选手档案。")
    impact = _delete_player_impact(data, users, player_id)
    blocking_labels = []
    if impact["appearances"]:
        blocking_labels.append(f"{impact['appearances']} 条出场记录")
    if impact["bindings"]:
        blocking_labels.append(f"{impact['bindings']} 个账号绑定")
    if impact["captain_team_ids"]:
        blocking_labels.append("担任战队队长")
    if impact["dimension_rows"]:
        blocking_labels.append(f"{impact['dimension_rows']} 条维度数据")
    if impact["award_references"]:
        blocking_labels.append(f"{impact['award_references']} 条奖项引用")
    if blocking_labels:
        raise ValueError("仍存在业务引用：" + "、".join(blocking_labels) + "。")
    for team in data.get("teams", []):
        team["members"] = [
            member_id
            for member_id in team.get("members", [])
            if str(member_id or "").strip() != player_id
        ]
    data["players"] = [
        item
        for item in data.get("players", [])
        if str(item.get("player_id") or "").strip() != player_id
    ]
    return impact


def _replace_user_player_id(user: dict[str, Any], source_id: str, target_id: str) -> None:
    changed = False
    if str(user.get("player_id") or "").strip() == source_id:
        user["player_id"] = target_id
        changed = True
    linked = [str(item or "").strip() for item in user.get("linked_player_ids", [])]
    if source_id in linked:
        linked = [target_id if item == source_id else item for item in linked]
        user["linked_player_ids"] = list(dict.fromkeys(item for item in linked if item))
        changed = True
    bound_players = user.get("bound_players")
    if isinstance(bound_players, list):
        for item in bound_players:
            if isinstance(item, dict) and str(item.get("player_id") or "").strip() == source_id:
                item["player_id"] = target_id
                changed = True
    if changed:
        user["user_player_bindings_write"] = True
        user["expected_user_authorization_etag"] = (
            legacy.build_user_authorization_etag(user)
        )


def _merge_player(
    data: dict[str, Any],
    users: list[dict[str, Any]],
    source_id: str,
    target_id: str,
    competition_name: str,
    season_name: str,
) -> int:
    source = next((item for item in data["players"] if item.get("player_id") == source_id), None)
    target = next((item for item in data["players"] if item.get("player_id") == target_id), None)
    if not source or not target:
        raise ValueError("源档案或目标档案不存在。")
    expected_scope = {(competition_name.strip(), season_name.strip())}
    player_scopes = _player_season_scope_map(data)
    if not all(expected_scope == player_scopes.get(player_id, set()) for player_id in (source_id, target_id)):
        raise ValueError("只能合并唯一归属于同一赛事赛季的选手档案。")
    _preserve_player_photo(source, target)
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
    player_scopes = _player_season_scope_map(data)
    team_by_id = {
        str(team.get("team_id") or "").strip(): team
        for team in data.get("teams", [])
        if str(team.get("team_id") or "").strip()
    }
    rows = []
    for player in players:
        player_id = str(player.get("player_id") or "").strip()
        appearances = _appearance_count(data, player_id)
        bindings = _bound_count(users, player_id)
        impact = _delete_player_impact(data, users, player_id)
        auto_created = _is_auto_created_player(player)
        if (
            appearances
            or bindings
            or impact["captain_team_ids"]
            or impact["dimension_rows"]
            or impact["award_references"]
            or not auto_created
        ):
            continue
        team = next((item for item in data.get("teams", []) if item.get("team_id") == player.get("team_id")), {})
        rows.append(
            f"<tr><td>{escape(player.get('display_name') or player_id)}</td><td><code>{escape(player_id)}</code></td>"
            f"<td>{escape(team.get('name') or '未归属战队')}</td><td><span class=\"chip\">无出场</span></td>"
            f"<td><form method=\"post\" action=\"/data-hygiene\" class=\"d-flex gap-2\"><input type=\"hidden\" name=\"action\" value=\"delete_empty\"><input type=\"hidden\" name=\"player_id\" value=\"{escape(player_id)}\"><input class=\"form-control form-control-sm\" name=\"confirmation\" placeholder=\"输入 {escape(player_id)} 确认\"><button class=\"btn btn-sm btn-outline-danger\" type=\"submit\">删除</button></form></td></tr>"
        )
    players_by_scope: dict[SeasonScope, list[dict[str, Any]]] = {}
    for player_id, player in player_by_id.items():
        scopes = player_scopes.get(player_id, set())
        if len(scopes) == 1:
            players_by_scope.setdefault(next(iter(scopes)), []).append(player)
    merge_scope_cards = []
    for (competition_name, season_name), scoped_players in sorted(players_by_scope.items()):
        if len(scoped_players) < 2:
            continue
        options = "".join(
            f'<option value="{escape(player_id)}">{escape(player.get("display_name") or player_id)} · {escape(team_by_id.get(str(player.get("team_id") or "").strip(), {}).get("name") or "未归属战队")} · {escape(player_id)} · 出场 {_appearance_count(data, player_id)} 局</option>'
            for player in sorted(
                scoped_players,
                key=lambda item: (str(item.get("display_name") or "").casefold(), str(item.get("player_id") or "")),
            )
            if (player_id := str(player.get("player_id") or "").strip())
        )
        merge_scope_cards.append(
            f"""
            <div class="border rounded p-3 p-lg-4 mb-3">
              <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
                <h3 class="h5 mb-0">{escape(competition_name)} · {escape(season_name)}</h3>
                <span class="chip">{len(scoped_players)} 个档案</span>
              </div>
              <form method="post" action="/data-hygiene" class="row g-3 align-items-end">
                <input type="hidden" name="action" value="merge_players">
                <input type="hidden" name="competition_name" value="{escape(competition_name)}">
                <input type="hidden" name="season_name" value="{escape(season_name)}">
                <div class="col-12 col-lg-4"><label class="form-label">源档案（会删除）</label><select class="form-select" name="source_player_id" required><option value="">请选择源档案</option>{options}</select></div>
                <div class="col-12 col-lg-4"><label class="form-label">目标档案（保留）</label><select class="form-select" name="target_player_id" required><option value="">请选择目标档案</option>{options}</select></div>
                <div class="col-12 col-lg-4"><label class="form-label">确认</label><input class="form-control" name="confirmation" placeholder="输入 合并 确认" required><button class="btn btn-dark mt-2" type="submit">执行合并</button></div>
              </form>
            </div>
            """
        )
    duplicate_rows = []
    for (competition_name, season_name), duplicate_players in _case_insensitive_duplicate_groups(players, player_scopes):
        profile_labels = "".join(
            f'<span class="chip me-2 mb-2">{escape(str(player.get("display_name") or player.get("player_id") or ""))} · {escape(str(player.get("player_id") or ""))}</span>'
            for player in duplicate_players
        )
        duplicate_rows.append(
            f"<tr><td>{escape(competition_name)} · {escape(season_name)}</td><td>{profile_labels}</td></tr>"
        )
    body = f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h1 class="section-title mb-2">档案清理与合并</h1>
      <p class="section-copy mb-0">合并会把源档案的比赛记录、奖项、阵容、维度数据和账号绑定迁移到目标档案；完成后源档案会被删除。源档案和目标档案必须唯一归属于同一个赛事赛季。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-wrap justify-content-between align-items-end gap-3 mb-3"><div><h2 class="section-title mb-2">疑似重复档案</h2><p class="section-copy mb-0">名称完全相同或仅英文字母大小写不同的档案会归为一组，例如 YAO、Yao 和 yao。</p></div><span class="chip">{len(duplicate_rows)} 组</span></div>
      <div class="table-responsive"><table class="table align-middle"><thead><tr><th>赛事赛季</th><th>疑似重复档案</th></tr></thead><tbody>{''.join(duplicate_rows) or '<tr><td colspan="2" class="text-secondary">暂无名称相同的疑似重复档案。</td></tr>'}</tbody></table></div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h2 class="section-title mb-2">按赛季合并选手档案</h2>
      <p class="section-copy mb-3">每个表单只列出同一赛事赛季内的档案；跨赛季档案不会出现在同一个合并表单中。</p>
      {''.join(merge_scope_cards) or '<div class="alert alert-secondary mb-0">当前没有可合并的同赛季选手档案。</div>'}
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
        try:
            next_data = deepcopy(data)
            impact = _delete_empty_player(next_data, users, player_id)
            errors = save_repository_state(next_data, users)
            if errors:
                raise ValueError("；".join(errors[:2]))
        except ValueError as exc:
            return redirect(
                start_response,
                append_alert_query("/data-hygiene", f"删除失败：{exc}"),
            )
        audit_action(
            ctx,
            "data_hygiene.delete_empty_player",
            target_type="player",
            target_id=player_id,
            summary=f"删除无出场自动档案 {player_id}",
            metadata=impact,
        )
        return redirect(start_response, append_alert_query("/data-hygiene", "已删除无出场自动档案。"))
    if action == "merge_players":
        source_id = form_value(ctx.form, "source_player_id").strip()
        target_id = form_value(ctx.form, "target_player_id").strip()
        competition_name = form_value(ctx.form, "competition_name").strip()
        season_name = form_value(ctx.form, "season_name").strip()
        if form_value(ctx.form, "confirmation").strip() != "合并" or not source_id or source_id == target_id:
            return redirect(start_response, append_alert_query("/data-hygiene", "请选定不同档案，并输入“合并”确认。"))
        try:
            next_data = deepcopy(data)
            next_users = deepcopy(users)
            moved = _merge_player(
                next_data,
                next_users,
                source_id,
                target_id,
                competition_name,
                season_name,
            )
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
            metadata={
                "source_player_id": source_id,
                "competition_name": competition_name,
                "season_name": season_name,
                "moved_appearances": moved,
            },
        )
        return redirect(start_response, append_alert_query("/data-hygiene", f"合并完成，已迁移 {moved} 条出场记录。"))
    return redirect(start_response, append_alert_query("/data-hygiene", "未知操作。"))
