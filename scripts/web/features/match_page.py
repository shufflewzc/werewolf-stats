from __future__ import annotations

import json

import web_app as legacy

Any = legacy.Any
account_role_label = legacy.account_role_label
MATCH_SCORE_COMPONENT_FIELDS = legacy.MATCH_SCORE_COMPONENT_FIELDS
RequestContext = legacy.RequestContext
RESULT_OPTIONS = legacy.RESULT_OPTIONS
STANCE_OPTIONS = legacy.STANCE_OPTIONS
STAGE_OPTIONS = legacy.STAGE_OPTIONS
build_match_day_path = legacy.build_match_day_path
build_match_next_path = legacy.build_match_next_path
build_scoped_path = legacy.build_scoped_path
can_manage_matches = legacy.can_manage_matches
escape = legacy.escape
form_value = legacy.form_value
get_match_by_id = legacy.get_match_by_id
get_match_competition_name = legacy.get_match_competition_name
get_match_score_model_label = legacy.get_match_score_model_label
layout = legacy.layout
load_validated_data = legacy.load_validated_data
normalize_match_score_model = legacy.normalize_match_score_model
normalize_score_breakdown = legacy.normalize_score_breakdown
normalize_stance_result = legacy.normalize_stance_result
quote = legacy.quote
start_response_json = legacy.start_response_json
to_chinese_camp = legacy.to_chinese_camp
urlencode = legacy.urlencode
uses_structured_score_model = legacy.uses_structured_score_model


def _build_match_legacy_href(ctx: RequestContext, match: dict[str, Any]) -> str:
    params: dict[str, str] = {}
    next_path = form_value(ctx.query, "next").strip()
    region = form_value(ctx.query, "region").strip()
    series = form_value(ctx.query, "series").strip()
    alert = form_value(ctx.query, "alert").strip()
    if next_path:
        params["next"] = next_path
    if region:
        params["region"] = region
    if series:
        params["series"] = series
    if alert:
        params["alert"] = alert
    if not params:
        return f"/matches/{match['match_id']}/legacy"
    return f"/matches/{match['match_id']}/legacy?{legacy.urlencode(params)}"


def _build_match_page_parts(ctx: RequestContext, match_id: str) -> tuple[str, str]:
    data = load_validated_data()
    match = get_match_by_id(data["matches"], match_id)
    if not match:
        return "未找到比赛", '<div class="alert alert-danger">没有找到对应的比赛。</div>'

    team_lookup = {team["team_id"]: team for team in data["teams"]}
    player_lookup = {player["player_id"]: player for player in data["players"]}
    competition_name = get_match_competition_name(match)
    season_name = str(match.get("season") or "").strip()
    selected_region = form_value(ctx.query, "region").strip() or None
    selected_series_slug = form_value(ctx.query, "series").strip() or None
    next_path = form_value(ctx.query, "next").strip() or build_match_next_path(match)
    score_model = normalize_match_score_model(match.get("score_model"))
    score_model_label = get_match_score_model_label(score_model)
    show_score_breakdown = uses_structured_score_model(score_model)
    participant_by_id = {
        str(participant.get("player_id") or "").strip(): participant
        for participant in match["players"]
        if str(participant.get("player_id") or "").strip()
    }
    legacy_href = _build_match_legacy_href(ctx, match)

    def render_award_player(player_id: str, empty_label: str) -> str:
        if not player_id:
            return f'<div class="small text-secondary">{escape(empty_label)}</div>'
        participant = participant_by_id.get(player_id)
        player = player_lookup.get(player_id)
        display_name = player["display_name"] if player else player_id
        detail_path = build_scoped_path(
            f"/players/{player_id}",
            competition_name,
            season_name,
            selected_region,
            selected_series_slug,
        )
        meta_parts = []
        if participant:
            seat = participant.get("seat")
            role = str(participant.get("role") or "").strip()
            team_name = team_lookup.get(participant.get("team_id"), {}).get(
                "name",
                str(participant.get("team_id") or "").strip(),
            )
            if seat:
                meta_parts.append(f"{seat}号")
            if role:
                meta_parts.append(role)
            if team_name:
                meta_parts.append(team_name)
        meta_html = ""
        if meta_parts:
            meta_html = f'<div class="small-muted mt-2">{" · ".join(escape(part) for part in meta_parts)}</div>'
        return (
            f'<a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover '
            f'fw-semibold fs-4" href="{escape(detail_path)}">{escape(display_name)}</a>'
            f"{meta_html}"
        )

    team_scores: dict[str, float] = {}
    for participant in match["players"]:
        team_scores.setdefault(participant["team_id"], 0.0)
        team_scores[participant["team_id"]] += float(participant["points_earned"])

    score_rows = [
        (
            team_id,
            team_lookup.get(team_id, {}).get("name", team_id),
            round(score, 2),
        )
        for team_id, score in sorted(
            team_scores.items(),
            key=lambda item: (-item[1], team_lookup.get(item[0], {}).get("name", item[0])),
        )
    ]
    scoreboard_html = "".join(
        f"""
        <div class="col-12 col-md-6">
          <div class="stat-card h-100 p-4 shadow-sm border-0">
            <div class="stat-label">战队积分</div>
            <div class="stat-value mt-2">{score:.2f}</div>
            <div class="small-muted mt-2">{escape(team_name)}</div>
          </div>
        </div>
        """
        for _, team_name, score in score_rows
    )
    winning_camp = str(match.get("winning_camp") or "").strip()
    awards_html = f"""
        <div class="col-12 col-md-4">
          <div class="stat-card h-100 p-4 shadow-sm border-0">
            <div class="stat-label">MVP</div>
            <div class="mt-2">{render_award_player(str(match.get('mvp_player_id') or '').strip(), '暂未设置 MVP')}</div>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="stat-card h-100 p-4 shadow-sm border-0">
            <div class="stat-label">SVP</div>
            <div class="mt-2">{render_award_player(str(match.get('svp_player_id') or '').strip(), '暂未设置 SVP')}</div>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="stat-card h-100 p-4 shadow-sm border-0">
            <div class="stat-label">背锅</div>
            <div class="mt-2">{
                '<div class="small text-secondary">好人胜利局不设背锅。</div>'
                if winning_camp == 'villagers'
                else render_award_player(str(match.get('scapegoat_player_id') or '').strip(), '暂未设置背锅选手')
            }</div>
          </div>
        </div>
    """

    participant_rows = []
    for participant in sorted(match["players"], key=lambda item: item["seat"]):
        player = player_lookup.get(participant["player_id"])
        team = team_lookup.get(participant["team_id"])
        player_name = player["display_name"] if player else participant["player_id"]
        team_name = team["name"] if team else participant["team_id"]
        stance_result = normalize_stance_result(participant)
        score_breakdown = normalize_score_breakdown(participant)
        breakdown_cells = ""
        if show_score_breakdown:
            breakdown_cells = "".join(
                f"<td>{score_breakdown[field_name]:.2f}</td>"
                for field_name, _ in MATCH_SCORE_COMPONENT_FIELDS
            )
        participant_rows.append(
            f"""
            <tr>
              <td>{participant['seat']}</td>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(build_scoped_path('/players/' + participant['player_id'], competition_name, season_name))}">{escape(player_name)}</a></td>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(build_scoped_path('/teams/' + participant['team_id'], competition_name, season_name))}">{escape(team_name)}</a></td>
              <td>{escape(participant['role'])}</td>
              <td>{escape(to_chinese_camp(participant['camp']))}</td>
              <td>{escape(RESULT_OPTIONS.get(participant['result'], participant['result']))}</td>
              {breakdown_cells}
              <td>{escape(STANCE_OPTIONS.get(stance_result, stance_result))}</td>
              <td>{float(participant['points_earned']):.2f}</td>
              <td>{escape(participant['notes'] or '无')}</td>
            </tr>
            """
        )

    breakdown_header_html = ""
    if show_score_breakdown:
        breakdown_header_html = "".join(
            f"<th>{escape(field_label)}</th>"
            for _, field_label in MATCH_SCORE_COMPONENT_FIELDS
        )

    edit_button = ""
    if can_manage_matches(ctx.current_user, data, competition_name):
        edit_button = (
            f'<a class="btn btn-dark" href="/matches/{escape(match_id)}/edit?next='
            f'{quote(build_scoped_path("/matches/" + match_id, competition_name, season_name))}">编辑比赛</a>'
        )

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">比赛详情页</div>
          <h1 class="hero-title mb-3">{escape(competition_name)} · {escape(season_name)}</h1>
          <p class="hero-copy mb-0">这里展示单场比赛的完整信息，包括比赛编号、阶段、参赛分组以及所有上场成员的个人明细。</p>
          <div class="d-flex flex-wrap gap-2 mt-4">
            <span class="chip">编号 {escape(match['match_id'])}</span>
            <span class="chip">{escape(STAGE_OPTIONS.get(match['stage'], match['stage']))}</span>
            <span class="chip">第 {match['round']} 轮</span>
            <span class="chip">计分模型 {escape(score_model_label)}</span>
            <a class="switcher-chip" href="{escape(build_match_day_path(match['played_on'], build_scoped_path('/matches/' + match_id, competition_name, season_name)))}">{escape(match['played_on'])}</a>
          </div>
          <div class="d-flex flex-wrap gap-2 mt-3">
            <a class="btn btn-outline-dark" href="{escape(next_path)}">返回上一页</a>
            {edit_button}
            <a class="btn btn-outline-dark" href="{escape(legacy_href)}">旧版比赛页</a>
          </div>
        </div>
        <div class="hero-stage-card">
          <div class="official-mark">Match Detail</div>
          <div class="hero-stage-label">Match Overview</div>
          <div class="hero-stage-title">{escape(match['match_id'])}</div>
          <div class="hero-stage-note">比赛详情页会固定当前系列赛和赛季口径，方便从战队页、队员页和赛事页继续回看单场内容。</div>
          <div class="hero-stage-grid">
            <div class="hero-stage-metric">
              <span>房间</span>
              <strong>{escape(match['table_label'])}</strong>
              <small>{escape(match['format'])}</small>
            </div>
            <div class="hero-stage-metric">
              <span>时长</span>
              <strong>{match['duration_minutes']} 分钟</strong>
              <small>完整比赛耗时</small>
            </div>
            <div class="hero-stage-metric">
              <span>胜利阵营</span>
              <strong>{escape(to_chinese_camp(match['winning_camp']))}</strong>
              <small>本局最终结果</small>
            </div>
            <div class="hero-stage-metric">
              <span>参赛分组</span>
              <strong>{escape(str(match.get('group_label') or '未设置'))}</strong>
              <small>本场所属分组</small>
            </div>
          </div>
        </div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">本局奖项</h2>
          <p class="section-copy mb-0">这里记录每场比赛的 MVP、SVP 和背锅选手；好人胜利局不会设置背锅。</p>
        </div>
      </div>
      <div class="row g-3">{awards_html}</div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">战队比分</h2>
          <p class="section-copy mb-0">按本场所有上场成员的得分累计展示，方便快速查看单场战队表现。</p>
        </div>
      </div>
      <div class="row g-3">{scoreboard_html}</div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">上场成员明细</h2>
          <p class="section-copy mb-0">点击队员或战队名称，可以继续跳转到对应的详情页，并保持当前系列赛与赛季口径。{escape('当前使用京城日报积分模型，已展开分项积分。' if show_score_breakdown else '')}</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>座位</th>
              <th>队员</th>
              <th>战队</th>
              <th>角色</th>
              <th>阵营</th>
              <th>结果</th>
              {breakdown_header_html}
              <th>站边</th>
              <th>得分</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            {''.join(participant_rows)}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <h2 class="section-title mb-2">比赛备注</h2>
      <p class="section-copy mb-0">{escape(match['notes'] or '暂无备注。')}</p>
    </section>
    """
    return f"{match['match_id']} 详情", body


def build_match_frontend_page(ctx: RequestContext, match_id: str) -> str:
    data = load_validated_data()
    match = get_match_by_id(data["matches"], match_id)
    if not match:
        return layout("未找到比赛", '<div class="alert alert-danger">没有找到对应的比赛。</div>', ctx)

    bootstrap = json.dumps(
        {
            "apiEndpoint": f"/api/matches/{match_id}",
            "alert": form_value(ctx.query, "alert").strip(),
            "legacyHref": _build_match_legacy_href(ctx, match),
        },
        ensure_ascii=False,
    )

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#122238">
    <title>{escape(str(match.get('match_id') or match_id))} 详情</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;800;900&family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/competitions-app.css">
  </head>
  <body class="competitions-app-shell match-detail-app-shell">
    <div class="shell-backdrop"></div>
    <header class="shell-header">
      <div class="shell-brand">
        <a class="shell-brand-link" href="/dashboard" aria-label="返回赛事首页">
          <span class="shell-brand-mark" aria-hidden="true"></span>
          <span>WOLF</span>
        </a>
        <span class="shell-brand-copy">比赛详情 · API Driven</span>
      </div>
      <nav class="shell-nav" aria-label="主导航">
        <a class="shell-nav-link" href="/dashboard">仪表盘</a>
        <a class="shell-nav-link is-active" href="/competitions">比赛中心</a>
        <a class="shell-nav-link" href="/teams">战队</a>
        <a class="shell-nav-link" href="/players">选手</a>
        <a class="shell-nav-link" href="/guilds">门派</a>
        <a class="shell-nav-link" href="/schedule">赛程日历</a>
      </nav>
      {_build_match_account_html(ctx)}
    </header>
    <main id="match-app" class="competitions-layout match-detail-layout" aria-live="polite">
      <section class="competitions-panel competitions-loading-shell">
        <div class="competitions-section-kicker">Loading Match</div>
        <h1 class="competitions-title">正在加载比赛详情</h1>
        <p class="competitions-copy">新前端会通过独立 API 拉取比赛概览、奖项、战队比分和上场成员。</p>
      </section>
    </main>
    <script>window.__WEREWOLF_MATCH_BOOTSTRAP__ = {bootstrap};</script>
    <script src="/assets/match-app.js" defer></script>
  </body>
</html>
"""


def _build_match_account_html(ctx: RequestContext) -> str:
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


def _serialize_match_detail_payload(ctx: RequestContext, match_id: str) -> dict[str, Any]:
    data = load_validated_data()
    match = get_match_by_id(data["matches"], match_id)
    legacy_href = _build_match_legacy_href(ctx, match or {"match_id": match_id})
    if not match:
        return {
            "not_found": True,
            "error": "没有找到对应的比赛。",
            "title": "未找到比赛",
            "alert": form_value(ctx.query, "alert").strip(),
            "legacy_href": legacy_href,
        }

    team_lookup = {team["team_id"]: team for team in data["teams"]}
    player_lookup = {player["player_id"]: player for player in data["players"]}
    competition_name = get_match_competition_name(match)
    season_name = str(match.get("season") or "").strip()
    selected_region = form_value(ctx.query, "region").strip() or None
    selected_series_slug = form_value(ctx.query, "series").strip() or None
    next_path = form_value(ctx.query, "next").strip() or build_match_next_path(match)
    score_model = normalize_match_score_model(match.get("score_model"))
    score_model_label = get_match_score_model_label(score_model)
    show_score_breakdown = uses_structured_score_model(score_model)
    participants = []
    team_scores: dict[str, float] = {}
    participant_by_id = {}
    for participant in sorted(match.get("players", []), key=lambda item: int(item.get("seat") or 0)):
        player_id = str(participant.get("player_id") or "").strip()
        team_id = str(participant.get("team_id") or "").strip()
        player = player_lookup.get(player_id, {})
        team = team_lookup.get(team_id, {})
        team_scores[team_id] = team_scores.get(team_id, 0.0) + float(participant.get("points_earned") or 0)
        participant_by_id[player_id] = participant
        breakdown = normalize_score_breakdown(participant) if show_score_breakdown else {}
        participants.append(
            {
                "seat": participant.get("seat") or 0,
                "player_id": player_id,
                "player_name": player.get("display_name") or player_id,
                "player_href": build_scoped_path(f"/players/{player_id}", competition_name, season_name, selected_region, selected_series_slug),
                "team_id": team_id,
                "team_name": team.get("name") or team_id,
                "team_href": build_scoped_path(f"/teams/{team_id}", competition_name, season_name, selected_region, selected_series_slug),
                "role": participant.get("role") or "",
                "camp": to_chinese_camp(participant.get("camp") or ""),
                "result": RESULT_OPTIONS.get(participant.get("result"), participant.get("result") or ""),
                "stance": STANCE_OPTIONS.get(normalize_stance_result(participant), normalize_stance_result(participant)),
                "points": round(float(participant.get("points_earned") or 0), 2),
                "notes": participant.get("notes") or "",
                "breakdown": {label: round(float(breakdown.get(field, 0.0)), 2) for field, label in MATCH_SCORE_COMPONENT_FIELDS} if show_score_breakdown else {},
            }
        )

    def award_payload(label: str, player_id: str, empty_label: str) -> dict[str, Any]:
        player_id = str(player_id or "").strip()
        participant = participant_by_id.get(player_id, {})
        player = player_lookup.get(player_id, {})
        team = team_lookup.get(str(participant.get("team_id") or ""), {})
        return {
            "label": label,
            "empty_label": empty_label,
            "player_id": player_id,
            "player_name": player.get("display_name") or (player_id if player_id else ""),
            "href": build_scoped_path(f"/players/{player_id}", competition_name, season_name, selected_region, selected_series_slug) if player_id else "",
            "meta": " · ".join(str(part) for part in [participant.get("seat") and f"{participant.get('seat')}号", participant.get("role"), team.get("name")] if part),
        }

    winning_camp = str(match.get("winning_camp") or "").strip()
    awards = [
        award_payload("MVP", str(match.get("mvp_player_id") or ""), "暂未设置 MVP"),
        award_payload("SVP", str(match.get("svp_player_id") or ""), "暂未设置 SVP"),
        {"label": "背锅", "empty_label": "好人胜利局不设背锅。", "player_id": "", "player_name": "", "href": "", "meta": ""}
        if winning_camp == "villagers"
        else award_payload("背锅", str(match.get("scapegoat_player_id") or ""), "暂未设置背锅选手"),
    ]
    scores = [
        {
            "team_id": team_id,
            "team_name": team_lookup.get(team_id, {}).get("name") or team_id,
            "href": build_scoped_path(f"/teams/{team_id}", competition_name, season_name, selected_region, selected_series_slug),
            "points": round(score, 2),
        }
        for team_id, score in sorted(team_scores.items(), key=lambda item: (-item[1], team_lookup.get(item[0], {}).get("name", item[0])))
    ]
    edit_href = ""
    if can_manage_matches(ctx.current_user, data, competition_name):
        edit_href = f"/matches/{quote(match_id)}/edit?next={quote(build_scoped_path('/matches/' + match_id, competition_name, season_name))}"

    return {
        "title": f"{match_id} 详情",
        "alert": form_value(ctx.query, "alert").strip(),
        "legacy_href": legacy_href,
        "match": {
            "match_id": match_id,
            "competition": competition_name,
            "season": season_name,
            "stage": STAGE_OPTIONS.get(match.get("stage"), match.get("stage") or ""),
            "round": match.get("round") or 0,
            "game_no": match.get("game_no") or 0,
            "played_on": match.get("played_on") or "",
            "day_href": build_match_day_path(match.get("played_on") or "", build_scoped_path('/matches/' + match_id, competition_name, season_name)),
            "table_label": match.get("table_label") or "",
            "format": match.get("format") or "",
            "duration_minutes": match.get("duration_minutes") or 0,
            "winning_camp": to_chinese_camp(match.get("winning_camp") or ""),
            "group_label": match.get("group_label") or "未设置",
            "score_model": score_model_label,
            "notes": match.get("notes") or "暂无备注。",
            "show_score_breakdown": show_score_breakdown,
        },
        "actions": {"next_href": next_path, "edit_href": edit_href, "legacy_href": legacy_href},
        "metrics": [
            {"label": "房间", "value": match.get("table_label") or "-", "copy": match.get("format") or "未记录板型"},
            {"label": "时长", "value": f"{match.get('duration_minutes') or 0} 分钟", "copy": "完整比赛耗时"},
            {"label": "胜利阵营", "value": to_chinese_camp(match.get("winning_camp") or ""), "copy": "本局最终结果"},
            {"label": "参赛分组", "value": match.get("group_label") or "未设置", "copy": "本场所属分组"},
        ],
        "awards": awards,
        "team_scores": scores,
        "participants": participants,
        "score_fields": [label for _, label in MATCH_SCORE_COMPONENT_FIELDS] if show_score_breakdown else [],
    }


def build_match_api_payload(ctx: RequestContext, match_id: str) -> dict[str, Any]:
    return _serialize_match_detail_payload(ctx, match_id)


def get_match_legacy_page(ctx: RequestContext, match_id: str) -> str:
    return legacy.get_match_page(ctx, match_id)


def handle_match_api(ctx: RequestContext, start_response, match_id: str):
    if ctx.method != "GET":
        return start_response_json(
            start_response,
            "405 Method Not Allowed",
            {"error": "match api only supports GET"},
            headers=[("Allow", "GET")],
        )
    payload = build_match_api_payload(ctx, match_id)
    status = "404 Not Found" if payload.get("not_found") else "200 OK"
    return start_response_json(start_response, status, payload)
