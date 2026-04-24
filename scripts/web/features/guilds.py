from __future__ import annotations

from html import escape
import json
import secrets
from typing import Any
import web_app as legacy

account_role_label = legacy.account_role_label
RequestContext = legacy.RequestContext
DEFAULT_PLAYER_PHOTO = legacy.DEFAULT_PLAYER_PHOTO
DEFAULT_TEAM_LOGO = legacy.DEFAULT_TEAM_LOGO
append_alert_query = legacy.append_alert_query
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
is_admin_user = legacy.is_admin_user
parse_team_scope_value = legacy.parse_team_scope_value
parse_username_list_text = legacy.parse_username_list_text
redirect = legacy.redirect
require_login = legacy.require_login
resolve_team_player_ids = legacy.resolve_team_player_ids
save_membership_requests = legacy.save_membership_requests
save_repository_state = legacy.save_repository_state
start_response_html = legacy.start_response_html
start_response_json = legacy.start_response_json
user_has_permission = legacy.user_has_permission
user_has_team_identity_in_scope = legacy.user_has_team_identity_in_scope
validate_guild_creation = legacy.validate_guild_creation
validate_team_creation = legacy.validate_team_creation


def can_manage_guild_honors(user: dict[str, Any] | None) -> bool:
    return is_admin_user(user) or user_has_permission(user, "guild_honor_manage")


def format_guild_honors_text(honors: list[dict[str, Any]] | None) -> str:
    rows: list[str] = []
    for item in honors or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        team_name = str(item.get("team_name") or "").strip()
        scope = str(item.get("scope") or "").strip()
        if not title and not team_name and not scope:
            continue
        rows.append(" | ".join([title, team_name, scope]))
    return "\n".join(rows)


def parse_guild_honors_text(value: str) -> tuple[list[dict[str, str]], str]:
    honors: list[dict[str, str]] = []
    for index, raw_line in enumerate(value.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3 or not all(parts):
            return [], f"第 {index} 行格式不正确，请使用“荣誉标题 | 战队名 | 赛事赛季”。"
        honors.append({"title": parts[0], "team_name": parts[1], "scope": parts[2]})
    return honors, ""


def build_guild_overview_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    guilds = sorted(data.get("guilds", []), key=lambda item: item["name"])
    team_guild_ids = {
        team["team_id"]: str(team.get("guild_id") or "").strip()
        for team in data["teams"]
    }
    guild_match_ids: dict[str, set[str]] = {}
    for match in data["matches"]:
        match_id = str(match.get("match_id") or "").strip()
        if not match_id:
            continue
        represented_guild_ids = {
            team_guild_ids.get(entry["team_id"], "")
            for entry in match.get("players", [])
        }
        for guild_id in represented_guild_ids:
            if guild_id:
                guild_match_ids.setdefault(guild_id, set()).add(match_id)

    rows: list[dict[str, Any]] = []
    for guild in guilds:
        guild_id = guild["guild_id"]
        guild_teams = [
            team
            for team in data["teams"]
            if str(team.get("guild_id") or "").strip() == guild_id
        ]
        ongoing_team_count = sum(
            1 for team in guild_teams if get_team_season_status(data, team) == "ongoing"
        )
        rows.append(
            {
                "guild_id": guild_id,
                "name": guild["name"],
                "short_name": str(guild.get("short_name") or "").strip(),
                "notes": str(guild.get("notes") or "").strip(),
                "leader_username": str(guild.get("leader_username") or "").strip(),
                "team_count": len(guild_teams),
                "ongoing_team_count": ongoing_team_count,
                "historical_team_count": max(len(guild_teams) - ongoing_team_count, 0),
                "match_count": len(guild_match_ids.get(guild_id, set())),
                "honor_count": len(build_guild_honor_rows(data, guild_id)),
                "guild": guild,
            }
        )
    return rows


def _serialize_guild_card(
    row: dict[str, Any],
    current_user: dict[str, Any] | None,
    can_manage_honors: bool,
) -> dict[str, Any]:
    guild = row["guild"]
    can_manage = can_manage_guild(current_user, guild) or can_manage_honors
    return {
        "guild_id": row["guild_id"],
        "name": row["name"],
        "short_name": row["short_name"] or "未设置简称",
        "notes": row["notes"] or "长期存在的战队组织。",
        "leader_username": row["leader_username"] or "未设置",
        "team_count": int(row["team_count"]),
        "ongoing_team_count": int(row["ongoing_team_count"]),
        "historical_team_count": int(row["historical_team_count"]),
        "match_count": int(row["match_count"]),
        "honor_count": int(row["honor_count"]),
        "href": f"/guilds/{row['guild_id']}",
        "manage_href": f"/guilds/{row['guild_id']}?view=manage" if can_manage else "",
    }


def build_guilds_api_payload(ctx: RequestContext) -> dict[str, Any]:
    data = load_validated_data()
    overview_rows = build_guild_overview_rows(data)
    can_manage_honors = can_manage_guild_honors(ctx.current_user)
    team_guild_ids = {
        team["team_id"]: str(team.get("guild_id") or "").strip()
        for team in data["teams"]
    }
    total_match_count = sum(
        1
        for match in data["matches"]
        if any(team_guild_ids.get(entry["team_id"], "") for entry in match.get("players", []))
    )
    featured_row = max(
        overview_rows,
        key=lambda item: (
            item["ongoing_team_count"],
            item["match_count"],
            item["honor_count"],
            item["team_count"],
            item["name"],
        ),
        default=None,
    )
    management_href = "/profile" if ctx.current_user else "/login?next=/profile"
    featured_payload = (
        {
            "name": featured_row["name"],
            "short_name": featured_row["short_name"] or "未设置简称",
            "notes": featured_row["notes"] or "长期存在的战队组织。",
            "href": f"/guilds/{featured_row['guild_id']}",
            "ongoing_team_count": int(featured_row["ongoing_team_count"]),
            "match_count": int(featured_row["match_count"]),
            "honor_count": int(featured_row["honor_count"]),
            "team_count": int(featured_row["team_count"]),
        }
        if featured_row
        else None
    )
    return {
        "alert": form_value(ctx.query, "alert").strip(),
        "hero": {
            "title": "全部门派",
            "copy": "这里是门派的对外展示入口。创建门派和管理操作继续收口在个人中心，公开页只负责浏览和下钻。",
            "featured": featured_payload,
        },
        "metrics": [
            {
                "label": "门派总数",
                "value": str(len(overview_rows)),
                "copy": "已登记的长期战队组织",
            },
            {
                "label": "进行中赛季战队",
                "value": str(sum(row["ongoing_team_count"] for row in overview_rows)),
                "copy": "当前仍在进行中的赛季身份",
            },
            {
                "label": "覆盖比赛",
                "value": str(total_match_count),
                "copy": "至少有门派战队参加的比赛数",
            },
            {
                "label": "历届荣誉",
                "value": str(sum(row["honor_count"] for row in overview_rows)),
                "copy": "门派归档荣誉条目",
            },
        ],
        "management": {
            "href": management_href,
            "label": "进入个人中心" if ctx.current_user else "登录后管理",
            "copy": (
                "门派创建和管理入口已经统一放进个人中心，公开页保持轻量浏览。"
                if ctx.current_user
                else "登录后可在个人中心创建门派、查看审核入口和进入管理页。"
            ),
        },
        "cards": [
            _serialize_guild_card(row, ctx.current_user, can_manage_honors)
            for row in overview_rows
        ],
        "legacy_href": "/guilds/legacy",
    }


def build_guilds_frontend_page(ctx: RequestContext) -> str:
    if ctx.current_user:
        display_name = ctx.current_user.get("display_name") or ctx.current_user["username"]
        role_label = account_role_label(ctx.current_user)
        account_html = f"""
        <div class="shell-account">
          <span class="shell-account-label">{escape(display_name)} · {escape(role_label)}</span>
          <a class="shell-button shell-button-secondary" href="/profile">控制台</a>
          <form method="post" action="/logout" class="shell-inline-form">
            <button type="submit" class="shell-button shell-button-secondary">退出</button>
          </form>
        </div>
        """
    else:
        account_html = """
        <div class="shell-account">
          <a class="shell-button shell-button-secondary" href="/login">登录</a>
          <a class="shell-button shell-button-primary" href="/register">注册</a>
        </div>
        """

    bootstrap = json.dumps(
        {
            "apiEndpoint": "/api/guilds",
            "alert": form_value(ctx.query, "alert").strip(),
        },
        ensure_ascii=False,
    )
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#122238">
    <title>门派</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;800;900&family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/guilds-app.css">
  </head>
  <body class="guilds-app-shell">
    <div class="shell-backdrop"></div>
    <header class="shell-header">
      <div class="shell-brand">
        <a class="shell-brand-link" href="/dashboard" aria-label="返回赛事首页">
          <span class="shell-brand-mark" aria-hidden="true"></span>
          <span>WOLF</span>
        </a>
        <span class="shell-brand-copy">门派系统 · API Driven</span>
      </div>
      <nav class="shell-nav" aria-label="主导航">
        <a class="shell-nav-link" href="/dashboard">仪表盘</a>
        <a class="shell-nav-link" href="/competitions">比赛中心</a>
        <a class="shell-nav-link" href="/teams">战队</a>
        <a class="shell-nav-link" href="/players">选手</a>
        <a class="shell-nav-link is-active" href="/guilds">门派</a>
        <a class="shell-nav-link" href="/schedule">赛程日历</a>
      </nav>
      {account_html}
    </header>
    <main id="guilds-app" class="guilds-app-root" aria-live="polite">
      <section class="guilds-loading-shell">
        <div class="guilds-loading-kicker">Loading Guilds</div>
        <h1>正在加载门派列表</h1>
        <p>新前端会通过独立 API 拉取门派概览并渲染页面。</p>
      </section>
    </main>
    <script>window.__WEREWOLF_GUILDS_BOOTSTRAP__ = {bootstrap};</script>
    <script src="/assets/guilds-app.js" defer></script>
  </body>
</html>
"""
def get_guilds_page(
    ctx: RequestContext,
    alert: str = "",
    form_values: dict[str, str] | None = None,
) -> str:
    data = load_validated_data()
    guild_rows = build_guild_overview_rows(data)
    cards = []
    for row in guild_rows:
        cards.append(
            f"""
            <div class="col-12 col-md-6 col-xl-4">
              <a class="team-link-card shadow-sm p-4 h-100" href="/guilds/{escape(row['guild_id'])}">
                <div class="card-kicker mb-2">门派</div>
                <h2 class="h4 mb-2">{escape(row['name'])}</h2>
                <div class="small-muted mb-3">{escape(row['notes'] or '长期存在的战队组织。')}</div>
                <div class="row g-3">
                  <div class="col-3"><div class="small text-secondary">进行中</div><div class="fw-semibold">{row['ongoing_team_count']}</div></div>
                  <div class="col-3"><div class="small text-secondary">比赛</div><div class="fw-semibold">{row['match_count']}</div></div>
                  <div class="col-3"><div class="small text-secondary">历届战队</div><div class="fw-semibold">{row['historical_team_count']}</div></div>
                  <div class="col-3"><div class="small text-secondary">荣誉</div><div class="fw-semibold">{row['honor_count']}</div></div>
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
    if get_team_season_status(data, team) == "completed":
        return "当前战队所属赛季已结束，不能再审核入门派申请。"
    current_guild_id = str(team.get("guild_id") or "").strip()
    if current_guild_id and current_guild_id != guild_id:
        return "该战队已经加入其他门派，不能重复通过旧申请。"
    return ""


def _build_guild_legacy_href(guild_id: str, manage_mode: bool) -> str:
    base_path = f"/guilds/{guild_id}/legacy"
    return f"{base_path}?view=manage" if manage_mode else base_path


def _build_guild_account_html(ctx: RequestContext) -> str:
    if ctx.current_user:
        display_name = ctx.current_user.get("display_name") or ctx.current_user["username"]
        role_label = account_role_label(ctx.current_user)
        return f"""
        <div class="shell-account">
          <span class="shell-account-label">{escape(display_name)} · {escape(role_label)}</span>
          <a class="shell-button shell-button-secondary" href="/profile">控制台</a>
          <form method="post" action="/logout" class="shell-inline-form">
            <button type="submit" class="shell-button shell-button-secondary">退出</button>
          </form>
        </div>
        """
    return """
        <div class="shell-account">
          <a class="shell-button shell-button-secondary" href="/login">登录</a>
          <a class="shell-button shell-button-primary" href="/register">注册</a>
        </div>
        """


def build_guild_frontend_page(ctx: RequestContext, guild_id: str) -> str:
    data = load_validated_data()
    guild = get_guild_by_id(data, guild_id)
    if not guild:
        return layout("未找到门派", '<div class="alert alert-danger">没有找到对应的门派。</div>', ctx)

    manage_mode = form_value(ctx.query, "view").strip() == "manage"
    bootstrap = json.dumps(
        {
            "apiEndpoint": f"/api/guilds/{guild_id}",
            "alert": form_value(ctx.query, "alert").strip(),
            "legacyHref": _build_guild_legacy_href(guild_id, manage_mode),
        },
        ensure_ascii=False,
    )
    account_html = _build_guild_account_html(ctx)
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#122238">
    <title>{escape(str(guild.get('name') or guild_id))} 门派页</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;800;900&family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/guilds-app.css">
  </head>
  <body class="guilds-app-shell guild-detail-app-shell">
    <div class="shell-backdrop"></div>
    <header class="shell-header">
      <div class="shell-brand">
        <a class="shell-brand-link" href="/dashboard" aria-label="返回赛事首页">
          <span class="shell-brand-mark" aria-hidden="true"></span>
          <span>WOLF</span>
        </a>
        <span class="shell-brand-copy">门派详情 · API Driven</span>
      </div>
      <nav class="shell-nav" aria-label="主导航">
        <a class="shell-nav-link" href="/dashboard">仪表盘</a>
        <a class="shell-nav-link" href="/competitions">比赛中心</a>
        <a class="shell-nav-link" href="/teams">战队</a>
        <a class="shell-nav-link" href="/players">选手</a>
        <a class="shell-nav-link is-active" href="/guilds">门派</a>
        <a class="shell-nav-link" href="/schedule">赛程日历</a>
      </nav>
      {account_html}
    </header>
    <main id="guild-app" class="guilds-app-root guild-detail-app-root" aria-live="polite">
      <section class="guilds-loading-shell">
        <div class="guilds-loading-kicker">Loading Guild</div>
        <h1>正在加载门派详情</h1>
        <p>前端会通过独立 API 拉取门派赛季战队、荣誉和管理信息。</p>
      </section>
    </main>
    <script>window.__WEREWOLF_GUILD_BOOTSTRAP__ = {bootstrap};</script>
    <script src="/assets/guild-app.js" defer></script>
  </body>
</html>
"""


def _build_guild_page_parts(ctx: RequestContext, guild_id: str) -> tuple[str, str]:
    data = load_validated_data()
    guild = get_guild_by_id(data, guild_id)
    if not guild:
        return "未找到门派", '<div class="alert alert-danger">没有找到对应的门派。</div>'
    manage_mode = form_value(ctx.query, "view").strip() == "manage"
    can_manage_membership = can_manage_guild(ctx.current_user, guild)
    can_manage_honors = can_manage_guild_honors(ctx.current_user)
    if manage_mode and not (can_manage_membership or can_manage_honors):
        return "没有权限", '<div class="alert alert-danger">你没有权限管理这个门派。</div>'
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
    if manage_mode and can_manage_membership:
        create_team_panel = """
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <h2 class="section-title mb-2">赛季战队来源</h2>
          <p class="section-copy mb-0">赛季战队不再由门派页手动创建。请先由赛事管理员批量创建，或在录入比赛结果时自动生成战队赛季档案；生成后再进入战队页认领、完善资料，并按需加入当前门派。</p>
        </section>
        """
    honor_manage_panel = ""
    if manage_mode and can_manage_honors:
        honor_manage_panel = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <h2 class="section-title mb-2">历届荣誉维护</h2>
          <p class="section-copy mb-3">每行一条，格式为：荣誉标题 | 战队名 | 赛事赛季。留空保存即可清空。</p>
          <form method="post" action="{manage_post_path}">
            <input type="hidden" name="action" value="update_guild_honors">
            <textarea class="form-control" name="honors_text" rows="8" placeholder="全国总冠军 | 狼王战队 | 2025 全国总决赛">{escape(format_guild_honors_text(guild.get('honors', [])))}</textarea>
            <button type="submit" class="btn btn-dark mt-3">保存历届荣誉</button>
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
        {f'<a class="btn btn-dark" href="/guilds/{escape(guild_id)}">查看对外页面</a>' if manage_mode else (f'<a class="btn btn-dark" href="/guilds/{escape(guild_id)}?view=manage">管理门派</a>' if (can_manage_membership or can_manage_honors) else '')}
      </div>
    </section>
    {summary_cards_html}
    {create_team_panel}
    {honor_manage_panel}
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
      if manage_mode and pending_requests and can_manage_membership
      else ''
    )}
    """
    return f"{guild['name']} 门派页", body


def get_guild_page(ctx: RequestContext, guild_id: str, alert: str = "") -> str:
    title, body = _build_guild_page_parts(ctx, guild_id)
    return layout(title, body, ctx, alert=alert)



def _serialize_guild_team_row(row: dict[str, Any], region_name: str | None = None, series_slug: str | None = None) -> dict[str, Any]:
    return {
        "team_id": row["team_id"],
        "team_name": row["team_name"],
        "competition_name": row["competition_name"],
        "season_name": row["season_name"],
        "status": row["status"],
        "status_label": row["status_label"],
        "matches": int(row["matches"]),
        "player_count": int(row["player_count"]),
        "points_total": f"{float(row['points_total']):.2f}",
        "href": build_scoped_path(
            "/teams/" + row["team_id"],
            row["competition_name"],
            row["season_name"],
            region_name,
            series_slug,
        ),
    }


def build_guild_detail_payload(ctx: RequestContext, guild_id: str) -> dict[str, Any]:
    data = load_validated_data()
    guild = get_guild_by_id(data, guild_id)
    manage_mode = form_value(ctx.query, "view").strip() == "manage"
    alert = form_value(ctx.query, "alert").strip()
    if not guild:
        return {
            "not_found": True,
            "title": "未找到门派",
            "alert": alert,
            "legacy_href": _build_guild_legacy_href(guild_id, manage_mode),
            "error": "没有找到对应的门派。",
        }

    can_manage_membership = can_manage_guild(ctx.current_user, guild)
    can_manage_honors = can_manage_guild_honors(ctx.current_user)
    if manage_mode and not (can_manage_membership or can_manage_honors):
        return {
            "forbidden": True,
            "title": "没有权限",
            "alert": alert,
            "legacy_href": _build_guild_legacy_href(guild_id, manage_mode),
            "error": "你没有权限管理这个门派。",
        }

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

    ongoing_rows = [row for row in competition_rows if row["status"] == "ongoing"]
    historical_rows = [row for row in competition_rows if row["status"] != "ongoing"]
    grouped_history: dict[str, list[dict[str, Any]]] = {}
    for row in historical_rows:
        grouped_history.setdefault(row["competition_name"], []).append(row)
    history_sections = [
        {
            "competition_name": competition_name,
            "team_count": len(rows),
            "points_total": f"{sum(float(item['points_total']) for item in rows):.2f}",
            "rows": [
                _serialize_guild_team_row(item)
                for item in sorted(
                    rows,
                    key=lambda item: (
                        get_team_season_status_rank(item["status"]),
                        item["season_name"],
                        item["team_name"],
                    ),
                )
            ],
        }
        for competition_name, rows in sorted(grouped_history.items(), key=lambda item: item[0])
    ]

    pending_requests = [
        item
        for item in load_membership_requests()
        if item["request_type"] == "guild_join" and item.get("target_guild_id") == guild_id
    ]
    manage_post_path = f"/guilds/{guild_id}?view=manage" if manage_mode else f"/guilds/{guild_id}"
    pending_payload = []
    if manage_mode and can_manage_membership:
        for item in pending_requests:
            team = get_team_by_id(data, item.get("source_team_id") or "")
            pending_payload.append(
                {
                    "request_id": item["request_id"],
                    "team_name": team["name"] if team else item.get("source_team_id") or "未知战队",
                    "scope": f"{item.get('scope_competition_name') or '未设置'} / {item.get('scope_season_name') or '未设置'}",
                    "username": item["username"],
                    "created_on": item["created_on"],
                }
            )

    title = f"{guild['name']} 门派页"
    return {
        "title": title,
        "alert": alert,
        "generated_at": china_now_label(),
        "legacy_href": _build_guild_legacy_href(guild_id, manage_mode),
        "manage_mode": manage_mode,
        "can_manage_membership": bool(can_manage_membership),
        "can_manage_honors": bool(can_manage_honors),
        "manage_href": f"/guilds/{guild_id}?view=manage" if (can_manage_membership or can_manage_honors) else "",
        "public_href": f"/guilds/{guild_id}",
        "manage_post_path": manage_post_path,
        "guild": {
            "guild_id": guild_id,
            "name": guild["name"],
            "short_name": str(guild.get("short_name") or "").strip() or "未设置简称",
            "notes": str(guild.get("notes") or "").strip() or "门派长期存在，可跨赛季组织多支战队。",
            "leader_username": str(guild.get("leader_username") or "").strip() or "未设置",
            "honors_text": format_guild_honors_text(guild.get("honors", [])),
        },
        "metrics": [
            {"label": "进行中赛季战队", "value": str(len(ongoing_rows)), "copy": "当前仍在进行中的赛季身份"},
            {"label": "累计赛季战队", "value": str(len(guild_teams)), "copy": "该门派历届赛季战队数量"},
            {"label": "累计比赛", "value": str(len(guild_match_ids)), "copy": "该门派战队参与过的比赛"},
            {"label": "历届荣誉", "value": str(len(honors)), "copy": "已归档荣誉条目"},
        ],
        "ongoing_teams": [_serialize_guild_team_row(row) for row in ongoing_rows],
        "history_sections": history_sections,
        "honors": [
            {"title": item["title"], "team_name": item["team_name"], "scope": item["scope"]}
            for item in honors
        ],
        "pending_requests": pending_payload,
        "management": {
            "profile_href": "/profile",
            "back_href": "/guilds",
            "source_copy": "赛季战队不再由门派页手动创建。请先由赛事管理员批量创建，或在录入比赛结果时自动生成战队赛季档案；生成后再进入战队页认领、完善资料，并按需加入当前门派。",
        },
    }

def build_guild_api_payload(ctx: RequestContext, guild_id: str) -> dict[str, Any]:
    return build_guild_detail_payload(ctx, guild_id)


def get_guild_legacy_page(ctx: RequestContext, guild_id: str, alert: str = "") -> str:
    return get_guild_page(ctx, guild_id, alert)

def handle_guilds(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", build_guilds_frontend_page(ctx))

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
                "honors": [],
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
        if get_team_season_status(data, team) == "completed":
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
                layout("没有权限", '<div class="alert alert-danger">只有具备战队管理权限的账号、已认领该战队的负责人或管理员可以申请加入门派。</div>', ctx),
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


def handle_guilds_api(ctx: RequestContext, start_response):
    if ctx.method != "GET":
        return start_response_json(
            start_response,
            "405 Method Not Allowed",
            {"error": "guilds api only supports GET"},
            headers=[("Allow", "GET")],
        )
    return start_response_json(
        start_response,
        "200 OK",
        build_guilds_api_payload(ctx),
    )


def handle_guild_api(ctx: RequestContext, start_response, guild_id: str):
    if ctx.method != "GET":
        return start_response_json(
            start_response,
            "405 Method Not Allowed",
            {"error": "guild api only supports GET"},
            headers=[("Allow", "GET")],
        )
    payload = build_guild_api_payload(ctx, guild_id)
    status = "404 Not Found" if payload.get("not_found") else ("403 Forbidden" if payload.get("forbidden") else "200 OK")
    return start_response_json(start_response, status, payload)


def handle_guild_page(ctx: RequestContext, start_response, guild_id: str):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", build_guild_frontend_page(ctx, guild_id))

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
    can_manage_membership = can_manage_guild(ctx.current_user, guild)
    can_manage_honors = can_manage_guild_honors(ctx.current_user)
    if action == "create_guild_team":
        redirect_path = f"/guilds/{guild_id}"
        if form_value(ctx.query, "view").strip() == "manage":
            redirect_path += "?view=manage"
        return redirect(
            start_response,
            append_alert_query(
                redirect_path,
                "赛季战队不再从门派页手动创建，请先由赛事管理员批量创建，或在录入比赛结果后自动生成。",
            ),
        )

    if action == "update_guild_honors":
        if not can_manage_honors:
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">只有管理员或被授予门派荣誉维护权限的账号可以编辑历届荣誉。</div>', ctx),
            )
        honors_text = form_value(ctx.form, "honors_text")
        honors, error = parse_guild_honors_text(honors_text)
        redirect_path = f"/guilds/{guild_id}?view=manage"
        if error:
            return redirect(
                start_response,
                append_alert_query(redirect_path, error),
            )
        guild["honors"] = honors
        errors = save_repository_state(data, users)
        if errors:
            return redirect(
                start_response,
                append_alert_query(redirect_path, "保存门派荣誉失败：" + "；".join(errors[:3])),
            )
        return redirect(
            start_response,
            append_alert_query(redirect_path, "门派历届荣誉已更新。"),
        )

    if action in {"approve_guild_join", "reject_guild_join"}:
        if not can_manage_membership:
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">只有门主、门派管理员或管理员可以审核入门派申请。</div>', ctx),
            )
        requests = load_membership_requests()
        request_id = form_value(ctx.form, "request_id").strip()
        redirect_path = f"/guilds/{guild_id}?view=manage"
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
            return redirect(
                start_response,
                append_alert_query(redirect_path, "没有找到对应的入门派申请。"),
            )
        if action == "reject_guild_join":
            requests = [item for item in requests if item["request_id"] != request_id]
            save_membership_requests(requests)
            return redirect(
                start_response,
                append_alert_query(redirect_path, "申请已拒绝。"),
            )
        team = get_team_by_id(data, request_item.get("source_team_id") or "")
        if not team:
            requests = [item for item in requests if item["request_id"] != request_id]
            save_membership_requests(requests)
            return redirect(
                start_response,
                append_alert_query(redirect_path, "申请对应的战队已经不存在，记录已移除。"),
            )
        approval_error = get_guild_join_approval_error(data, team, guild_id)
        if approval_error:
            return redirect(
                start_response,
                append_alert_query(redirect_path, approval_error),
            )
        team["guild_id"] = guild_id
        errors = save_repository_state(data, users)
        if errors:
            return redirect(
                start_response,
                append_alert_query(redirect_path, "审核失败：" + "；".join(errors[:3])),
            )
        requests = [item for item in requests if item["request_id"] != request_id]
        save_membership_requests(requests)
        return redirect(
            start_response,
            append_alert_query(redirect_path, f"已通过 {team['name']} 的入门派申请。"),
        )

    return start_response_html(
        start_response,
        "405 Method Not Allowed",
        layout("请求无效", '<div class="alert alert-danger">未识别的门派详情操作。</div>', ctx),
    )
