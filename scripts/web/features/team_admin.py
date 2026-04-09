from __future__ import annotations

from html import escape
import web_app as legacy

RequestContext = legacy.RequestContext
build_scoped_path = legacy.build_scoped_path
form_value = legacy.form_value
get_team_by_id = legacy.get_team_by_id
get_team_scope = legacy.get_team_scope
get_team_season_status = legacy.get_team_season_status
get_team_season_status_label = legacy.get_team_season_status_label
is_admin_user = legacy.is_admin_user
layout = legacy.layout
list_team_scopes = legacy.list_team_scopes
load_membership_requests = legacy.load_membership_requests
load_users = legacy.load_users
load_validated_data = legacy.load_validated_data
redirect = legacy.redirect
save_membership_requests = legacy.save_membership_requests
save_repository_state = legacy.save_repository_state
start_response_html = legacy.start_response_html

from web.features.team_center import dissolve_team, get_team_dissolution_error


def build_scope_options(data: dict, selected_scope: str) -> str:
    options = ['<option value="">全部赛事赛季</option>']
    for scope in list_team_scopes(data, {"ongoing", "upcoming", "completed"}):
        status_label = {
            "ongoing": "进行中",
            "upcoming": "未开始",
            "completed": "已结束",
        }.get(scope.get("status", ""), "未配置")
        options.append(
            f'<option value="{escape(scope["value"])}"{" selected" if selected_scope == scope["value"] else ""}>'
            f'{escape(scope["label"])} · {escape(status_label)}</option>'
        )
    return "".join(options)


def get_team_admin_page(ctx: RequestContext, alert: str = "") -> str:
    data = load_validated_data()
    requests = load_membership_requests()
    users = load_users()
    selected_scope = form_value(ctx.query, "scope").strip()
    keyword = form_value(ctx.query, "keyword").strip().lower()
    selected_competition, selected_season = legacy.parse_team_scope_value(selected_scope)

    request_count_by_team: dict[str, int] = {}
    for request in requests:
        team_id = str(request.get("target_team_id") or "").strip()
        if team_id:
            request_count_by_team[team_id] = request_count_by_team.get(team_id, 0) + 1

    match_count_by_team: dict[str, int] = {}
    for match in data["matches"]:
        seen_team_ids: set[str] = set()
        for participant in match.get("players", []):
            team_id = str(participant.get("team_id") or "").strip()
            if not team_id or team_id in seen_team_ids:
                continue
            seen_team_ids.add(team_id)
            match_count_by_team[team_id] = match_count_by_team.get(team_id, 0) + 1

    filtered_teams = []
    for team in data["teams"]:
        competition_name, season_name = get_team_scope(team)
        if selected_scope and (competition_name, season_name) != (selected_competition, selected_season):
            continue
        if keyword:
            haystacks = [
                str(team.get("name") or "").lower(),
                str(team.get("short_name") or "").lower(),
                competition_name.lower(),
                season_name.lower(),
            ]
            if not any(keyword in value for value in haystacks):
                continue
        filtered_teams.append(team)

    filtered_teams.sort(
        key=lambda item: (
            legacy.get_team_season_status_rank(get_team_season_status(data, item)),
            item.get("competition_name", ""),
            item.get("season_name", ""),
            item["name"],
        )
    )

    rows = []
    for team in filtered_teams:
        competition_name, season_name = get_team_scope(team)
        team_id = team["team_id"]
        linked_users = [
            user["username"]
            for user in users
            if any(player_id in team.get("members", []) for player_id in legacy.get_user_bound_player_ids(user))
        ]
        rows.append(
            f"""
            <tr>
              <td>
                <div class="fw-semibold">{escape(team['name'])}</div>
                <div class="small text-secondary">{escape(team['short_name'])} · {escape(team_id)}</div>
              </td>
              <td>{escape(competition_name)}<div class="small text-secondary">{escape(season_name)}</div></td>
              <td>{escape(get_team_season_status_label(get_team_season_status(data, team)))}</td>
              <td>{len(team.get('members', []))}</td>
              <td>{match_count_by_team.get(team_id, 0)}</td>
              <td>{request_count_by_team.get(team_id, 0)}</td>
              <td>{escape('、'.join(linked_users) if linked_users else '无')}</td>
              <td>
                <div class="d-flex flex-wrap gap-2">
                  <a class="btn btn-sm btn-outline-dark" href="{escape(build_scoped_path(f'/teams/{team_id}', competition_name, season_name))}">查看</a>
                  <form method="post" action="/team-admin" class="m-0">
                    <input type="hidden" name="action" value="delete_team">
                    <input type="hidden" name="team_id" value="{escape(team_id)}">
                    <button type="submit" class="btn btn-sm btn-outline-danger">删除</button>
                  </form>
                </div>
              </td>
            </tr>
            """
        )

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">管理员入口</div>
      <h1 class="display-6 fw-semibold mb-3">战队管理</h1>
      <p class="mb-0 opacity-75">集中管理赛季战队。你可以按赛事赛季筛选、查看战队状态，并在这里直接删除战队。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <form method="get" action="/team-admin" class="row g-3 align-items-end">
        <div class="col-12 col-lg-5">
          <label class="form-label">赛事赛季</label>
          <select class="form-select" name="scope">{build_scope_options(data, selected_scope)}</select>
        </div>
        <div class="col-12 col-lg-5">
          <label class="form-label">关键词</label>
          <input class="form-control" name="keyword" value="{escape(form_value(ctx.query, 'keyword').strip())}" placeholder="搜索战队名、简称、赛事或赛季">
        </div>
        <div class="col-12 col-lg-2 d-flex gap-2">
          <button type="submit" class="btn btn-dark flex-fill">筛选</button>
          <a class="btn btn-outline-dark" href="/team-admin">重置</a>
        </div>
      </form>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">战队总表</h2>
          <p class="section-copy mb-0">当前共筛选出 {len(filtered_teams)} 支战队。</p>
        </div>
        <a class="btn btn-outline-dark" href="/teams">返回公开战队页</a>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>战队</th>
              <th>赛事赛季</th>
              <th>状态</th>
              <th>成员数</th>
              <th>比赛数</th>
              <th>申请数</th>
              <th>绑定账号</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>{''.join(rows) or '<tr><td colspan="8" class="text-secondary">当前没有符合条件的战队。</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    """
    return layout("战队管理", body, ctx, alert=alert)


def handle_team_admin(ctx: RequestContext, start_response):
    if not is_admin_user(ctx.current_user):
        return start_response_html(
            start_response,
            "403 Forbidden",
            layout("没有权限", '<div class="alert alert-danger">只有管理员可以访问战队管理页面。</div>', ctx),
        )

    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_team_admin_page(ctx))

    if form_value(ctx.form, "action").strip() != "delete_team":
        return start_response_html(
            start_response,
            "200 OK",
            get_team_admin_page(ctx, alert="未识别的操作。"),
        )

    team_id = form_value(ctx.form, "team_id").strip()
    data = load_validated_data()
    users = load_users()
    team = get_team_by_id(data, team_id)
    if not team:
        return start_response_html(
            start_response,
            "200 OK",
            get_team_admin_page(ctx, alert="没有找到要删除的战队。"),
        )

    dissolution_error = get_team_dissolution_error(data, team, "删除战队")
    if dissolution_error:
        return start_response_html(
            start_response,
            "200 OK",
            get_team_admin_page(ctx, alert=dissolution_error),
        )

    users, requests = dissolve_team(data, users, team)
    errors = save_repository_state(data, users)
    if errors:
        return start_response_html(
            start_response,
            "200 OK",
            get_team_admin_page(ctx, alert="删除战队失败：" + "；".join(errors[:3])),
        )
    save_membership_requests(requests)
    return redirect(start_response, "/team-admin")
