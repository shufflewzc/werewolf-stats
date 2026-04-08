from __future__ import annotations

from html import escape
import secrets
from typing import Any
import web_app as legacy

RequestContext = legacy.RequestContext
DEFAULT_PLAYER_PHOTO = legacy.DEFAULT_PLAYER_PHOTO
DEFAULT_TEAM_LOGO = legacy.DEFAULT_TEAM_LOGO
append_user_player_binding = legacy.append_user_player_binding
build_guild_honor_rows = legacy.build_guild_honor_rows
build_scoped_path = legacy.build_scoped_path
build_team_serial = legacy.build_team_serial
build_unique_slug = legacy.build_unique_slug
can_manage_guild = legacy.can_manage_guild
can_manage_team = legacy.can_manage_team
china_now_label = legacy.china_now_label
china_today_label = legacy.china_today_label
form_value = legacy.form_value
get_guild_by_id = legacy.get_guild_by_id
get_match_competition_name = legacy.get_match_competition_name
get_team_by_id = legacy.get_team_by_id
get_team_page = legacy.get_team_page
get_team_scope = legacy.get_team_scope
get_team_season_status = legacy.get_team_season_status
get_team_season_status_label = legacy.get_team_season_status_label
get_team_season_status_rank = legacy.get_team_season_status_rank
get_user_player = legacy.get_user_player
layout = legacy.layout
list_ongoing_team_scopes = legacy.list_ongoing_team_scopes
load_membership_requests = legacy.load_membership_requests
load_users = legacy.load_users
load_validated_data = legacy.load_validated_data
parse_team_scope_value = legacy.parse_team_scope_value
parse_username_list_text = legacy.parse_username_list_text
redirect = legacy.redirect
require_login = legacy.require_login
resolve_team_player_ids = legacy.resolve_team_player_ids
save_membership_requests = legacy.save_membership_requests
save_repository_state = legacy.save_repository_state
start_response_html = legacy.start_response_html
user_has_permission = legacy.user_has_permission
user_has_team_identity_in_scope = legacy.user_has_team_identity_in_scope
validate_guild_creation = legacy.validate_guild_creation
validate_team_creation = legacy.validate_team_creation
def get_guilds_page(
    ctx: RequestContext,
    alert: str = "",
    form_values: dict[str, str] | None = None,
) -> str:
    data = load_validated_data()
    guilds = sorted(data.get("guilds", []), key=lambda item: item["name"])
    cards = []
    for guild in guilds:
        guild_teams = [
            team for team in data["teams"] if str(team.get("guild_id") or "").strip() == guild["guild_id"]
        ]
        guild_team_count = len(guild_teams)
        ongoing_team_count = sum(1 for team in guild_teams if get_team_season_status(data, team) == "ongoing")
        guild_match_count = sum(
            1
            for match in data["matches"]
            if any(
                str(get_team_by_id(data, entry["team_id"]) and get_team_by_id(data, entry["team_id"]).get("guild_id") or "").strip()
                == guild["guild_id"]
                for entry in match["players"]
            )
        )
        honor_count = len(build_guild_honor_rows(data, guild["guild_id"]))
        cards.append(
            f"""
            <div class="col-12 col-md-6 col-xl-4">
              <a class="team-link-card shadow-sm p-4 h-100" href="/guilds/{escape(guild['guild_id'])}">
                <div class="card-kicker mb-2">门派</div>
                <h2 class="h4 mb-2">{escape(guild['name'])}</h2>
                <div class="small-muted mb-3">{escape(guild['notes'] or '长期存在的战队组织。')}</div>
                <div class="row g-3">
                  <div class="col-4"><div class="small text-secondary">进行中</div><div class="fw-semibold">{ongoing_team_count}</div></div>
                  <div class="col-4"><div class="small text-secondary">比赛</div><div class="fw-semibold">{guild_match_count}</div></div>
                  <div class="col-4"><div class="small text-secondary">历届战队</div><div class="fw-semibold">{max(guild_team_count - ongoing_team_count, 0)}</div></div>
                </div>
              </a>
            </div>
            """
        )

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">门派展示页</div>
      <h1 class="display-6 fw-semibold mb-3">全部门派</h1>
      <p class="mb-0 opacity-75">这里是门派的对外展示入口。创建门派和门派管理操作已经统一放进个人中心。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <h2 class="section-title mb-3">全部门派</h2>
      <div class="row g-3 g-lg-4">{''.join(cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">当前还没有门派，可前往个人中心创建。</div></div>'}</div>
    </section>
    """
    return layout("门派", body, ctx, alert=alert)


def get_guild_join_approval_error(
    data: dict[str, Any],
    team: dict[str, Any] | None,
    guild_id: str,
) -> str:
    if not team:
        return "申请对应的战队已经不存在。"
    if get_team_season_status(data, team) != "ongoing":
        return "当前战队所属赛季已结束，不能再审核入门派申请。"
    current_guild_id = str(team.get("guild_id") or "").strip()
    if current_guild_id and current_guild_id != guild_id:
        return "该战队已经加入其他门派，不能重复通过旧申请。"
    return ""


def get_guild_page(ctx: RequestContext, guild_id: str, alert: str = "") -> str:
    data = load_validated_data()
    guild = get_guild_by_id(data, guild_id)
    if not guild:
        return layout("未找到门派", '<div class="alert alert-danger">没有找到对应的门派。</div>', ctx)
    manage_mode = form_value(ctx.query, "view").strip() == "manage"
    if manage_mode and not can_manage_guild(ctx.current_user, guild):
        return layout("没有权限", '<div class="alert alert-danger">你没有权限管理这个门派。</div>', ctx)
    guild_teams = [
        team for team in data["teams"] if str(team.get("guild_id") or "").strip() == guild_id
    ]
    guild_teams.sort(
        key=lambda team: (
            get_team_season_status_rank(get_team_season_status(data, team)),
            team.get("competition_name", ""),
            team.get("season_name", ""),
            team["name"],
        )
    )
    honors = build_guild_honor_rows(data, guild_id)
    competition_rows: list[dict[str, Any]] = []
    guild_match_ids: set[str] = set()
    for team in guild_teams:
        competition_name, season_name = get_team_scope(team)
        team_status = get_team_season_status(data, team)
        scoped_matches = [
            match
            for match in data["matches"]
            if (match.get("season") or "").strip() == season_name
            and get_match_competition_name(match) == competition_name
            and any(entry["team_id"] == team["team_id"] for entry in match["players"])
        ]
        guild_match_ids.update(match["match_id"] for match in scoped_matches)
        points_total = sum(
            float(entry["points_earned"])
            for match in scoped_matches
            for entry in match["players"]
            if entry["team_id"] == team["team_id"]
        )
        player_count = len(resolve_team_player_ids(data, team["team_id"], competition_name, season_name))
        competition_rows.append(
            {
                "team_id": team["team_id"],
                "team_name": team["name"],
                "competition_name": competition_name,
                "season_name": season_name,
                "status": team_status,
                "status_label": get_team_season_status_label(team_status),
                "matches": len(scoped_matches),
                "player_count": player_count,
                "points_total": round(points_total, 2),
            }
        )
    pending_requests = [
        item
        for item in load_membership_requests()
        if item["request_type"] == "guild_join" and item.get("target_guild_id") == guild_id
    ]
    manage_post_path = f"/guilds/{escape(guild_id)}?view=manage" if manage_mode else f"/guilds/{escape(guild_id)}"
    ongoing_rows = [row for row in competition_rows if row["status"] == "ongoing"]
    historical_rows = [row for row in competition_rows if row["status"] != "ongoing"]
    featured_rows = ongoing_rows
    team_cards = "".join(
        f"""
        <div class="col-12 col-md-6">
          <a class="team-link-card shadow-sm p-4 h-100" href="{escape(build_scoped_path('/teams/' + row['team_id'], row['competition_name'], row['season_name']))}">
            <div class="d-flex justify-content-between align-items-start gap-3">
              <div>
                <div class="card-kicker mb-2">{escape(row['status_label'])}</div>
                <h2 class="h4 mb-1">{escape(row['team_name'])}</h2>
                <div class="small-muted">{escape(row['competition_name'])} · {escape(row['season_name'])}</div>
              </div>
              <span class="chip">查看战队</span>
            </div>
            <div class="row g-3 mt-2">
              <div class="col-6"><div class="small text-secondary">对局</div><div class="fw-semibold">{row['matches']}</div></div>
              <div class="col-3"><div class="small text-secondary">队员</div><div class="fw-semibold">{row['player_count']}</div></div>
              <div class="col-3"><div class="small text-secondary">总积分</div><div class="fw-semibold">{row['points_total']:.2f}</div></div>
            </div>
          </a>
        </div>
        """
        for row in featured_rows
    )
    grouped_rows: dict[str, list[dict[str, Any]]] = {}
    for row in historical_rows:
        grouped_rows.setdefault(row["competition_name"], []).append(row)
    competition_sections = []
    for competition_name, rows in sorted(grouped_rows.items(), key=lambda item: item[0]):
        sorted_rows = sorted(
            rows,
            key=lambda item: (
                get_team_season_status_rank(item["status"]),
                item["season_name"],
                item["team_name"],
            ),
        )
        rows_html = "".join(
            f"""
            <tr>
              <td>{escape(item['season_name'])}</td>
              <td>{escape(item['team_name'])}</td>
              <td>{escape(item['status_label'])}</td>
              <td>{item['player_count']}</td>
              <td>{item['matches']}</td>
              <td>{item['points_total']:.2f}</td>
              <td><a class="btn btn-sm btn-outline-dark" href="{escape(build_scoped_path('/teams/' + item['team_id'], item['competition_name'], item['season_name']))}">查看详情</a></td>
            </tr>
            """
            for item in sorted_rows
        )
        competition_sections.append(
            f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-3">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
                <div>
                  <h2 class="section-title mb-2">{escape(competition_name)}</h2>
                  <p class="section-copy mb-0">这里收起展示这个门派在 {escape(competition_name)} 的历届赛季战队，默认不打开展示。</p>
                </div>
                <div class="d-flex flex-wrap gap-2">
                  <span class="chip">历届战队 {len(sorted_rows)} 支</span>
                  <span class="chip">总积分 {sum(item['points_total'] for item in sorted_rows):.2f}</span>
                </div>
              </div>
              <div class="table-responsive">
                <table class="table align-middle">
                  <thead><tr><th>赛季</th><th>战队</th><th>状态</th><th>队员</th><th>对局</th><th>总积分</th><th>操作</th></tr></thead>
                  <tbody>{rows_html}</tbody>
                </table>
              </div>
            </section>
            """
        )
    ongoing_team_count = sum(1 for row in competition_rows if row["status"] == "ongoing")
    historical_sections_html = "".join(competition_sections)
    history_panel_html = (
        f"""
        <details class="panel shadow-sm p-3 p-lg-4 mb-4">
          <summary class="fw-semibold" style="cursor:pointer;">展开查看历届赛季战队</summary>
          <div class="mt-3">
            {historical_sections_html or '<div class="alert alert-secondary mb-0">当前还没有可展示的历届赛季战队。</div>'}
          </div>
        </details>
        """
        if historical_rows
        else ""
    )
    summary_cards_html = f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-3">
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">进行中赛季战队</div><div class="stat-value mt-2">{ongoing_team_count}</div></div></div>
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">累计赛季战队</div><div class="stat-value mt-2">{len(guild_teams)}</div></div></div>
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">累计比赛</div><div class="stat-value mt-2">{len(guild_match_ids)}</div></div></div>
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">历届荣誉</div><div class="stat-value mt-2">{len(honors)}</div></div></div>
      </div>
    </section>
    """
    honor_rows_html = "".join(
        f"<tr><td>{escape(item['title'])}</td><td>{escape(item['team_name'])}</td><td>{escape(item['scope'])}</td></tr>"
        for item in honors
    )
    request_rows_html = "".join(
        f"""
        <tr>
          <td>{escape(get_team_by_id(data, item.get('source_team_id') or '')['name'] if get_team_by_id(data, item.get('source_team_id') or '') else item.get('source_team_id') or '未知战队')}</td>
          <td>{escape(item.get('scope_competition_name') or '未设置')} / {escape(item.get('scope_season_name') or '未设置')}</td>
          <td>{escape(item['username'])}</td>
          <td>{escape(item['created_on'])}</td>
          <td>
            <div class="d-flex flex-wrap gap-2">
              <form method="post" action="{manage_post_path}" class="m-0">
                <input type="hidden" name="action" value="approve_guild_join">
                <input type="hidden" name="request_id" value="{escape(item['request_id'])}">
                <button type="submit" class="btn btn-sm btn-dark">通过</button>
              </form>
              <form method="post" action="{manage_post_path}" class="m-0">
                <input type="hidden" name="action" value="reject_guild_join">
                <input type="hidden" name="request_id" value="{escape(item['request_id'])}">
                <button type="submit" class="btn btn-sm btn-outline-danger">拒绝</button>
              </form>
            </div>
          </td>
        </tr>
        """
        for item in pending_requests
    )
    create_team_panel = ""
    if manage_mode and can_manage_guild(ctx.current_user, guild):
        scope_options = "".join(
            f'<option value="{escape(scope["value"])}">{escape(scope["label"])}</option>'
            for scope in list_ongoing_team_scopes(data)
        )
        create_team_panel = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <h2 class="section-title mb-2">为门派创建赛季战队</h2>
          <p class="section-copy mb-4">门主或门派管理员可以直接创建某个正在进行赛季的战队，并指定队长账号。</p>
          <form method="post" action="{manage_post_path}">
            <input type="hidden" name="action" value="create_guild_team">
            <div class="row g-3">
              <div class="col-12">
                <label class="form-label">赛事赛季</label>
                <select class="form-select" name="team_scope">{scope_options}</select>
              </div>
              <div class="col-12 col-lg-6">
                <label class="form-label">战队名称</label>
                <input class="form-control" name="team_name">
              </div>
              <div class="col-12 col-lg-6">
                <label class="form-label">战队简称</label>
                <input class="form-control" name="short_name">
              </div>
              <div class="col-12 col-lg-6">
                <label class="form-label">队长账号</label>
                <input class="form-control" name="captain_username" placeholder="留空则默认当前账号">
              </div>
              <div class="col-12">
                <label class="form-label">战队说明</label>
                <textarea class="form-control" name="notes" rows="3"></textarea>
              </div>
            </div>
            <button type="submit" class="btn btn-dark mt-4">创建门派战队</button>
          </form>
        </section>
        """

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">{'门派管理页' if manage_mode else '门派详情页'}</div>
      <h1 class="display-6 fw-semibold mb-3">{escape(guild['name'])}</h1>
      <p class="mb-2 opacity-75">门主账号：{escape(guild['leader_username'])}</p>
      <p class="mb-0 opacity-75">{escape(guild['notes'] or '门派长期存在，可跨赛季组织多支战队。')}</p>
      <div class="d-flex flex-wrap gap-2 mt-3">
        <a class="btn btn-outline-dark" href="/guilds">返回门派列表</a>
        <a class="btn btn-outline-dark" href="/profile">进入个人中心</a>
        {f'<a class="btn btn-dark" href="/guilds/{escape(guild_id)}">查看对外页面</a>' if manage_mode else (f'<a class="btn btn-dark" href="/guilds/{escape(guild_id)}?view=manage">管理门派</a>' if can_manage_guild(ctx.current_user, guild) else '')}
      </div>
    </section>
    {summary_cards_html}
    {create_team_panel}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h2 class="section-title mb-3">当前进行中的赛季战队</h2>
      <p class="section-copy mb-3">这里只展示已经加入该门派、且所在赛季仍在进行中的战队。历届赛季战队默认折叠，可按需展开查看。</p>
      <div class="row g-3 g-lg-4">{team_cards or '<div class="col-12"><div class="alert alert-secondary mb-0">该门派当前没有进行中的赛季战队。</div></div>'}</div>
    </section>
    {history_panel_html}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h2 class="section-title mb-3">历届荣誉</h2>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead><tr><th>荣誉</th><th>战队</th><th>赛事赛季</th></tr></thead>
          <tbody>{honor_rows_html or '<tr><td colspan="3" class="text-secondary">当前还没有可归档的荣誉。</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    {(
      f'''
      <section class="panel shadow-sm p-3 p-lg-4">
        <h2 class="section-title mb-3">待审核的战队入门派申请</h2>
        <div class="table-responsive">
          <table class="table align-middle">
            <thead><tr><th>战队</th><th>赛事赛季</th><th>申请账号</th><th>申请时间</th><th>操作</th></tr></thead>
            <tbody>{request_rows_html}</tbody>
          </table>
        </div>
      </section>
      '''
      if manage_mode and pending_requests and can_manage_guild(ctx.current_user, guild)
      else ''
    )}
    """
    return layout(f"{guild['name']} 门派页", body, ctx, alert=alert)

def handle_guilds(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_guilds_page(ctx))

    guard = require_login(ctx, start_response)
    if guard is not None:
        return guard

    action = form_value(ctx.form, "action").strip()
    data = load_validated_data()
    users = load_users()
    if action == "create_guild":
        if not user_has_permission(ctx.current_user, "guild_manage"):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">只有具备门派管理权限的账号才能创建门派。</div>', ctx),
            )
        name = form_value(ctx.form, "name").strip()
        short_name = form_value(ctx.form, "short_name").strip()
        manager_usernames_text = form_value(ctx.form, "manager_usernames")
        notes = form_value(ctx.form, "notes").strip()
        manager_usernames = [
            username
            for username in parse_username_list_text(manager_usernames_text)
            if username != ctx.current_user["username"]
        ]
        error = validate_guild_creation(
            name,
            short_name,
            manager_usernames,
            data.get("guilds", []),
            users,
        )
        if error:
            return start_response_html(
                start_response,
                "200 OK",
                get_guilds_page(
                    ctx,
                    alert=error,
                    form_values={
                        "name": name,
                        "short_name": short_name,
                        "manager_usernames": manager_usernames_text,
                        "notes": notes,
                    },
                ),
            )
        data.setdefault("guilds", []).append(
            {
                "guild_id": build_unique_slug(
                    {guild["guild_id"] for guild in data.get("guilds", [])},
                    "guild",
                    name,
                    "guild",
                ),
                "name": name,
                "short_name": short_name,
                "logo": DEFAULT_TEAM_LOGO,
                "active": True,
                "founded_on": china_today_label(),
                "leader_username": ctx.current_user["username"],
                "manager_usernames": manager_usernames,
                "notes": notes or "由网站创建的长期门派组织。",
            }
        )
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_guilds_page(ctx, alert="创建门派失败：" + "；".join(errors[:3])),
            )
        return redirect(start_response, "/guilds")

    if action == "request_team_guild_join":
        guild_id = form_value(ctx.form, "guild_id").strip()
        team_id = form_value(ctx.form, "team_id").strip()
        guild = get_guild_by_id(data, guild_id)
        team = get_team_by_id(data, team_id)
        if not guild or not team:
            return start_response_html(
                start_response,
                "200 OK",
                get_guilds_page(ctx, alert="没有找到要申请加入的门派或战队。"),
            )
        if team.get("guild_id"):
            return start_response_html(
                start_response,
                "200 OK",
                get_team_page(ctx, team_id, alert="当前战队已经加入门派。"),
            )
        if get_team_season_status(data, team) != "ongoing":
            return start_response_html(
                start_response,
                "200 OK",
                get_team_page(ctx, team_id, alert="当前战队所属赛季已结束，不能再申请加入门派。"),
            )
        current_player = get_user_player(data, ctx.current_user)
        if not can_manage_team(ctx, team, current_player):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">只有具备战队管理权限的账号、战队队长或管理员可以申请加入门派。</div>', ctx),
            )
        requests = load_membership_requests()
        if any(
            item["request_type"] == "guild_join"
            and item.get("source_team_id") == team_id
            and item.get("target_guild_id") == guild_id
            for item in requests
        ):
            return start_response_html(
                start_response,
                "200 OK",
                get_team_page(ctx, team_id, alert="当前战队已经提交过这个门派申请。"),
            )
        competition_name, season_name = get_team_scope(team)
        requests.append(
            {
                "request_id": secrets.token_urlsafe(12),
                "request_type": "guild_join",
                "username": ctx.current_user["username"],
                "display_name": ctx.current_user.get("display_name") or ctx.current_user["username"],
                "player_id": team.get("captain_player_id"),
                "source_team_id": team_id,
                "target_team_id": "",
                "target_guild_id": guild_id,
                "scope_competition_name": competition_name,
                "scope_season_name": season_name,
                "created_on": china_now_label(),
            }
        )
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_team_page(ctx, team_id, alert=f"已向门派 {guild['name']} 提交加入申请。"),
        )

    return start_response_html(
        start_response,
        "405 Method Not Allowed",
        layout("请求无效", '<div class="alert alert-danger">未识别的门派操作。</div>', ctx),
    )

def handle_guild_page(ctx: RequestContext, start_response, guild_id: str):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_guild_page(ctx, guild_id))

    guard = require_login(ctx, start_response)
    if guard is not None:
        return guard

    data = load_validated_data()
    users = load_users()
    guild = get_guild_by_id(data, guild_id)
    if not guild:
        return start_response_html(
            start_response,
            "404 Not Found",
            layout("未找到门派", '<div class="alert alert-danger">没有找到对应的门派。</div>', ctx),
        )

    action = form_value(ctx.form, "action").strip()
    if action == "create_guild_team":
        if not can_manage_guild(ctx.current_user, guild):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">只有门主、门派管理员或管理员可以创建门派战队。</div>', ctx),
            )
        selected_scope = form_value(ctx.form, "team_scope").strip()
        competition_name, season_name = parse_team_scope_value(selected_scope)
        team_name = form_value(ctx.form, "team_name").strip()
        short_name = form_value(ctx.form, "short_name").strip()
        captain_username = form_value(ctx.form, "captain_username").strip() or ctx.current_user["username"]
        notes = form_value(ctx.form, "notes").strip()
        captain_user = next((user for user in users if user["username"] == captain_username), None)
        if not captain_user:
            return start_response_html(
                start_response,
                "200 OK",
                get_guild_page(ctx, guild_id, alert="指定的队长账号不存在。"),
            )
        if selected_scope not in {scope["value"] for scope in list_ongoing_team_scopes(data)}:
            return start_response_html(
                start_response,
                "200 OK",
                get_guild_page(ctx, guild_id, alert="请为门派战队选择一个正在进行中的赛季。"),
            )
        if user_has_team_identity_in_scope(data, captain_user, competition_name, season_name):
            return start_response_html(
                start_response,
                "200 OK",
                get_guild_page(ctx, guild_id, alert="指定的队长账号在这个赛事赛季里已经有战队身份。"),
            )
        error = validate_team_creation(
            team_name,
            short_name,
            competition_name,
            season_name,
            data["teams"],
        )
        if error:
            return start_response_html(
                start_response,
                "200 OK",
                get_guild_page(ctx, guild_id, alert=error),
            )
        existing_player_ids = {player["player_id"] for player in data["players"]}
        player_id = build_unique_slug(existing_player_ids, "player", captain_username, "player")
        team_id = build_team_serial(data, competition_name, season_name, data["teams"])
        data["players"].append(
            {
                "player_id": player_id,
                "display_name": captain_user.get("display_name") or captain_username,
                "team_id": team_id,
                "photo": DEFAULT_PLAYER_PHOTO,
                "aliases": [],
                "active": True,
                "joined_on": china_today_label(),
                "notes": f"由门派 {guild['name']} 创建的赛季战队队长身份。",
            }
        )
        data["teams"].append(
            {
                "team_id": team_id,
                "name": team_name,
                "short_name": short_name,
                "logo": DEFAULT_TEAM_LOGO,
                "active": True,
                "founded_on": china_today_label(),
                "competition_name": competition_name,
                "season_name": season_name,
                "guild_id": guild_id,
                "captain_player_id": player_id,
                "members": [player_id],
                "notes": notes or f"由门派 {guild['name']} 创建。",
            }
        )
        users = append_user_player_binding(users, captain_username, player_id)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_guild_page(ctx, guild_id, alert="创建门派战队失败：" + "；".join(errors[:3])),
            )
        return redirect(
            start_response,
            build_scoped_path(f"/teams/{team_id}", competition_name, season_name),
        )

    if action in {"approve_guild_join", "reject_guild_join"}:
        if not can_manage_guild(ctx.current_user, guild):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">只有门主、门派管理员或管理员可以审核入门派申请。</div>', ctx),
            )
        requests = load_membership_requests()
        request_id = form_value(ctx.form, "request_id").strip()
        request_item = next(
            (
                item
                for item in requests
                if item["request_id"] == request_id
                and item["request_type"] == "guild_join"
                and item.get("target_guild_id") == guild_id
            ),
            None,
        )
        if not request_item:
            return start_response_html(
                start_response,
                "200 OK",
                get_guild_page(ctx, guild_id, alert="没有找到对应的入门派申请。"),
            )
        if action == "reject_guild_join":
            requests = [item for item in requests if item["request_id"] != request_id]
            save_membership_requests(requests)
            return start_response_html(
                start_response,
                "200 OK",
                get_guild_page(ctx, guild_id, alert="申请已拒绝。"),
            )
        team = get_team_by_id(data, request_item.get("source_team_id") or "")
        if not team:
            requests = [item for item in requests if item["request_id"] != request_id]
            save_membership_requests(requests)
            return start_response_html(
                start_response,
                "200 OK",
                get_guild_page(ctx, guild_id, alert="申请对应的战队已经不存在，记录已移除。"),
            )
        approval_error = get_guild_join_approval_error(data, team, guild_id)
        if approval_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_guild_page(ctx, guild_id, alert=approval_error),
            )
        team["guild_id"] = guild_id
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_guild_page(ctx, guild_id, alert="审核失败：" + "；".join(errors[:3])),
            )
        requests = [item for item in requests if item["request_id"] != request_id]
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_guild_page(ctx, guild_id, alert=f"已通过 {team['name']} 的入门派申请。"),
        )

    return start_response_html(
        start_response,
        "405 Method Not Allowed",
        layout("请求无效", '<div class="alert alert-danger">未识别的门派详情操作。</div>', ctx),
    )
