from __future__ import annotations

import json

import web_app as legacy

Any = legacy.Any
account_role_label = legacy.account_role_label
build_player_rows = legacy.build_player_rows
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
format_pct = legacy.format_pct
get_player_dimension_history = legacy.get_player_dimension_history
is_placeholder_match = legacy.is_placeholder_match
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
safe_rate = legacy.safe_rate
summarize_dimension_rows = legacy.summarize_dimension_rows

PREDICTION_BUCKETS = [
    ("lt_2", "小于2分", "<", 2.0),
    ("lt_5", "小于5分", "<", 5.0),
    ("lt_7", "小于7分", "<", 7.0),
    ("gt_7", "大于7分", ">", 7.0),
    ("gt_12", "大于12分", ">", 12.0),
    ("gt_14_5", "大于14.5分", ">", 14.5),
]


def _is_completed_prediction_match(match: dict[str, Any], current_match_id: str) -> bool:
    if str(match.get("match_id") or "") == current_match_id:
        return False
    if is_placeholder_match(match):
        return False
    participants = match.get("players", [])
    if not participants:
        return False
    if any(float(item.get("points_earned") or 0.0) > 0 for item in participants):
        return True
    return bool(
        str(match.get("mvp_player_id") or "").strip()
        or str(match.get("svp_player_id") or "").strip()
        or str(match.get("scapegoat_player_id") or "").strip()
    )


def _collect_player_point_samples(
    data: dict[str, Any],
    player_id: str,
    competition_name: str,
    season_name: str,
    current_match_id: str,
) -> tuple[list[float], list[float]]:
    current_season_points: list[float] = []
    other_season_points: list[float] = []
    for match in data.get("matches", []):
        if not _is_completed_prediction_match(match, current_match_id):
            continue
        match_competition = get_match_competition_name(match)
        match_season = str(match.get("season") or "").strip()
        for participant in match.get("players", []):
            if str(participant.get("player_id") or "").strip() != player_id:
                continue
            points = float(participant.get("points_earned") or 0.0)
            if match_competition == competition_name and match_season == season_name:
                current_season_points.append(points)
            else:
                other_season_points.append(points)
            break
    return current_season_points, other_season_points


def _find_player_row(
    data: dict[str, Any],
    player_id: str,
    competition_name: str | None,
    season_name: str | None,
) -> dict[str, Any] | None:
    rows = build_player_rows(data, competition_name, season_name)
    return next((row for row in rows if row.get("player_id") == player_id and int(row.get("games_played") or 0) > 0), None)


def _build_dimension_anchor(
    data: dict[str, Any],
    player_id: str,
    competition_name: str,
    season_name: str,
) -> dict[str, float]:
    current_rows = [
        row
        for row in get_player_dimension_history(data, player_id, competition_name, season_name)
        if str(row.get("season_name") or "").strip() == season_name
    ]
    if not current_rows:
        return {"games": 0.0, "avg_points": 0.0, "win_rate": 0.0, "mvp_rate": 0.0}
    summary = summarize_dimension_rows(current_rows)
    games = float(summary.get("games_played") or 0.0)
    return {
        "games": games,
        "avg_points": safe_rate(float(summary.get("daily_points") or 0.0), games),
        "win_rate": safe_rate(float(summary.get("wins") or 0.0), games),
        "mvp_rate": safe_rate(float(summary.get("mvp_count") or 0.0), games),
    }


def _weighted_probability(samples: list[tuple[float, float]], operator: str, threshold: float) -> float:
    total_weight = sum(weight for _, weight in samples)
    if total_weight <= 0:
        return 0.0
    if operator == "<":
        matched = sum(weight for value, weight in samples if value < threshold)
    else:
        matched = sum(weight for value, weight in samples if value > threshold)
    return matched / total_weight


def score_prediction_labels() -> list[dict[str, str]]:
    return [{"key": key, "label": label} for key, label, _, _ in PREDICTION_BUCKETS]


def empty_manual_prediction() -> dict[str, float | None]:
    return {key: None for key, _, _, _ in PREDICTION_BUCKETS}


def normalize_manual_prediction(raw_item: dict[str, Any] | None) -> dict[str, float | None]:
    result = empty_manual_prediction()
    if not isinstance(raw_item, dict):
        return result
    for key, _, _, _ in PREDICTION_BUCKETS:
        raw_value = raw_item.get(key)
        if raw_value in (None, ""):
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if value > 1:
            value = value / 100.0
        result[key] = max(0.0, min(1.0, value))
    return result


def load_manual_score_predictions() -> dict[str, dict[str, dict[str, float | None]]]:
    raw_value = legacy.load_meta_value("manual_score_predictions") or ""
    if not raw_value.strip():
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    result: dict[str, dict[str, dict[str, float | None]]] = {}
    if not isinstance(parsed, dict):
        return result
    for match_id, player_items in parsed.items():
        if not isinstance(player_items, dict):
            continue
        normalized_match_id = str(match_id or "").strip()
        if not normalized_match_id:
            continue
        result[normalized_match_id] = {}
        for player_id, values in player_items.items():
            normalized_player_id = str(player_id or "").strip()
            if not normalized_player_id:
                continue
            result[normalized_match_id][normalized_player_id] = normalize_manual_prediction(values)
        if not result[normalized_match_id]:
            result.pop(normalized_match_id, None)
    return result


def save_manual_score_predictions(payload: dict[str, dict[str, dict[str, float | None]]]) -> None:
    clean_payload: dict[str, dict[str, dict[str, float]]] = {}
    for match_id, player_items in payload.items():
        normalized_match_id = str(match_id or "").strip()
        if not normalized_match_id or not isinstance(player_items, dict):
            continue
        clean_payload[normalized_match_id] = {}
        for player_id, values in player_items.items():
            normalized_player_id = str(player_id or "").strip()
            normalized_values = normalize_manual_prediction(values)
            clean_values = {
                key: float(value)
                for key, value in normalized_values.items()
                if value is not None
            }
            if normalized_player_id and clean_values:
                clean_payload[normalized_match_id][normalized_player_id] = clean_values
        if not clean_payload[normalized_match_id]:
            clean_payload.pop(normalized_match_id, None)
    legacy.save_meta_value("manual_score_predictions", json.dumps(clean_payload, ensure_ascii=False))


def apply_manual_score_predictions(
    predictions: list[dict[str, Any]],
    match_id: str,
) -> list[dict[str, Any]]:
    manual_by_player = load_manual_score_predictions().get(match_id, {})
    for item in predictions:
        manual_values = normalize_manual_prediction(manual_by_player.get(str(item.get("player_id") or "")))
        manual_payload = []
        for key, label, _, _ in PREDICTION_BUCKETS:
            value = manual_values.get(key)
            manual_payload.append(
                {
                    "key": key,
                    "label": label,
                    "value": value,
                    "display": format_pct(float(value)) if value is not None else "未填写",
                }
            )
        item["manual_probabilities"] = manual_payload
    return predictions


def build_match_score_predictions(
    data: dict[str, Any],
    match: dict[str, Any],
    competition_name: str,
    season_name: str,
    selected_region: str | None,
    selected_series_slug: str | None,
) -> list[dict[str, Any]]:
    player_lookup = {player["player_id"]: player for player in data.get("players", [])}
    team_lookup = {team["team_id"]: team for team in data.get("teams", [])}
    current_match_id = str(match.get("match_id") or "")
    stats_data = {
        "teams": data.get("teams", []),
        "players": data.get("players", []),
        "matches": [
            row
            for row in data.get("matches", [])
            if _is_completed_prediction_match(row, current_match_id)
        ],
    }
    predictions: list[dict[str, Any]] = []
    for participant in sorted(match.get("players", []), key=lambda item: int(item.get("seat") or 0)):
        player_id = str(participant.get("player_id") or "").strip()
        if not player_id:
            continue
        current_points, other_points = _collect_player_point_samples(
            data,
            player_id,
            competition_name,
            season_name,
            current_match_id,
        )
        player_row = _find_player_row(stats_data, player_id, competition_name, season_name)
        all_row = _find_player_row(stats_data, player_id, None, None)
        dimension = _build_dimension_anchor(data, player_id, competition_name, season_name)
        weighted_samples: list[tuple[float, float]] = [(value, 1.0) for value in current_points]
        weighted_samples.extend((value, 0.45) for value in other_points)
        current_avg = (
            float(player_row.get("average_points") or 0.0)
            if player_row
            else (sum(current_points) / len(current_points) if current_points else 0.0)
        )
        current_win_rate = float(player_row.get("win_rate") or 0.0) if player_row else 0.0
        all_avg = float(all_row.get("average_points") or 0.0) if all_row else 0.0
        anchor_candidates = [value for value in [current_avg, dimension["avg_points"], all_avg] if value > 0]
        anchor = sum(anchor_candidates) / len(anchor_candidates) if anchor_candidates else 7.0
        adjusted_anchor = max(
            0.0,
            anchor
            + (current_win_rate - 0.5) * 1.6
            + (dimension["win_rate"] - 0.5) * 1.2
            + dimension["mvp_rate"] * 2.0,
        )
        pseudo_weight = max(0.8, min(3.0, (dimension["games"] * 0.18) + (1.0 if player_row else 0.0)))
        weighted_samples.append((adjusted_anchor, pseudo_weight))
        if not current_points and other_points:
            weighted_samples.append((sum(other_points) / len(other_points), 1.1))
        probabilities = [
            {
                "key": key,
                "label": label,
                "value": round(_weighted_probability(weighted_samples, operator, threshold), 4),
                "display": format_pct(_weighted_probability(weighted_samples, operator, threshold)),
            }
            for key, label, operator, threshold in PREDICTION_BUCKETS
        ]
        sample_weight = sum(weight for _, weight in weighted_samples)
        if len(current_points) >= 6:
            confidence = "较高"
        elif len(current_points) >= 3 or sample_weight >= 4:
            confidence = "中等"
        else:
            confidence = "偏低"
        predictions.append(
            {
                "seat": int(participant.get("seat") or 0),
                "player_id": player_id,
                "player_name": player_lookup.get(player_id, {}).get("display_name") or player_id,
                "player_href": build_scoped_path(f"/players/{player_id}", competition_name, season_name, selected_region, selected_series_slug),
                "team_name": team_lookup.get(str(participant.get("team_id") or ""), {}).get("name") or str(participant.get("team_id") or ""),
                "current_samples": len(current_points),
                "reference_samples": len(other_points),
                "dimension_games": int(dimension["games"]),
                "expected_points": f"{adjusted_anchor:.2f}",
                "win_rate": format_pct(current_win_rate),
                "confidence": confidence,
                "probabilities": probabilities,
            }
        )
    return apply_manual_score_predictions(predictions, current_match_id)


def _format_manual_input_value(value: float | None) -> str:
    if value is None:
        return ""
    return f"{float(value) * 100:.1f}".rstrip("0").rstrip(".")


def render_prediction_table_html(
    predictions: list[dict[str, Any]],
    *,
    table_class: str = "table align-middle",
    dark_links: bool = True,
) -> str:
    system_headers = "".join(f"<th>系统 {escape(label)}</th>" for _, label, _, _ in PREDICTION_BUCKETS)
    manual_headers = "".join(f"<th>人工 {escape(label)}</th>" for _, label, _, _ in PREDICTION_BUCKETS)
    rows = []
    for item in predictions:
        system_by_key = {entry["key"]: entry for entry in item.get("probabilities", [])}
        manual_by_key = {entry["key"]: entry for entry in item.get("manual_probabilities", [])}
        link_class = "link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" if dark_links else ""
        player_html = (
            f'<a class="{link_class}" href="{escape(item.get("player_href") or "#")}">{escape(item.get("player_name") or "")}</a>'
            if item.get("player_href")
            else escape(item.get("player_name") or "")
        )
        system_cells = "".join(
            f"<td>{escape(system_by_key.get(key, {}).get('display', '0.0%'))}</td>"
            for key, _, _, _ in PREDICTION_BUCKETS
        )
        manual_cells = "".join(
            f"<td>{escape(manual_by_key.get(key, {}).get('display', '未填写'))}</td>"
            for key, _, _, _ in PREDICTION_BUCKETS
        )
        rows.append(
            f"""
            <tr>
              <td>{escape(str(item.get('seat') or ''))}</td>
              <td>{player_html}</td>
              <td>{escape(item.get('team_name') or '')}</td>
              <td>{escape(item.get('expected_points') or '')}</td>
              <td>{escape(item.get('win_rate') or '')}</td>
              {system_cells}
              {manual_cells}
              <td>{escape(item.get('confidence') or '')}</td>
              <td>本赛季 {int(item.get('current_samples') or 0)} 场 · 其他赛季 {int(item.get('reference_samples') or 0)} 场 · 维度 {int(item.get('dimension_games') or 0)} 局</td>
            </tr>
            """
        )
    return f"""
    <div class="table-responsive">
      <table class="{escape(table_class)}">
        <thead>
          <tr><th>座位</th><th>队员</th><th>战队</th><th>预测均分</th><th>本季胜率</th>{system_headers}{manual_headers}<th>置信度</th><th>依据</th></tr>
        </thead>
        <tbody>{''.join(rows) or '<tr><td colspan="20" class="text-secondary">请先录入本场参赛选手名单。</td></tr>'}</tbody>
      </table>
    </div>
    """


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
        if not player:
            return f'<span class="fw-semibold fs-4">{escape(display_name)}</span>{meta_html}'
        detail_path = build_scoped_path(
            f"/players/{player_id}",
            competition_name,
            season_name,
            selected_region,
            selected_series_slug,
        )
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
              <td>{
                f'<a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(build_scoped_path("/players/" + participant["player_id"], competition_name, season_name))}">{escape(player_name)}</a>'
                if player
                else f'<span class="fw-semibold">{escape(player_name)}</span>'
              }</td>
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
    predictions = build_match_score_predictions(
        data,
        match,
        competition_name,
        season_name,
        selected_region,
        selected_series_slug,
    )
    prediction_panel = f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">胜率预测</h2>
          <p class="section-copy mb-0">预测已拆分到独立页面展示，前台会并排显示系统计算概率和后台人工概率。</p>
        </div>
        <div class="d-flex flex-wrap gap-2">
          <a class="btn btn-dark" href="/matches/{escape(match_id)}/predictions?next={quote(build_scoped_path('/matches/' + match_id, competition_name, season_name))}">打开预测页</a>
          <a class="btn btn-outline-dark" href="/prediction-admin?match_id={escape(match_id)}">后台人工概率</a>
        </div>
      </div>
      <div class="alert alert-warning fw-semibold mb-0">当前本场已有 {len(predictions)} 名选手可预测。预测仅用于赛前参考；未录入结果的比赛不会计入历史样本。</div>
    </section>
    """

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
    {prediction_panel}
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


def _build_match_prediction_context(ctx: RequestContext, match_id: str) -> tuple[dict[str, Any] | None, str]:
    data = load_validated_data()
    match = get_match_by_id(data["matches"], match_id)
    if not match:
        return None, "没有找到对应的比赛。"
    competition_name = get_match_competition_name(match)
    season_name = str(match.get("season") or "").strip()
    selected_region = form_value(ctx.query, "region").strip() or None
    selected_series_slug = form_value(ctx.query, "series").strip() or None
    predictions = build_match_score_predictions(
        data,
        match,
        competition_name,
        season_name,
        selected_region,
        selected_series_slug,
    )
    return {
        "data": data,
        "match": match,
        "competition_name": competition_name,
        "season_name": season_name,
        "selected_region": selected_region,
        "selected_series_slug": selected_series_slug,
        "predictions": predictions,
    }, ""


def get_match_prediction_page(ctx: RequestContext, match_id: str, alert: str = "") -> str:
    context, error = _build_match_prediction_context(ctx, match_id)
    if not context:
        return layout("胜率预测", f'<div class="alert alert-danger">{escape(error)}</div>', ctx)
    match = context["match"]
    competition_name = context["competition_name"]
    season_name = context["season_name"]
    next_path = form_value(ctx.query, "next").strip() or build_scoped_path("/matches/" + match_id, competition_name, season_name)
    table_html = render_prediction_table_html(context["predictions"])
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">Score Forecast</div>
          <h1 class="hero-title mb-3">胜率预测</h1>
          <p class="hero-copy mb-0">系统计算概率和后台人工概率并排展示，适合在赛前录入参赛名单后做分数区间判断。</p>
          <div class="d-flex flex-wrap gap-2 mt-4">
            <span class="chip">{escape(competition_name)}</span>
            <span class="chip">{escape(season_name)}</span>
            <span class="chip">比赛 {escape(match_id)}</span>
            <span class="chip">{escape(STAGE_OPTIONS.get(match.get('stage'), match.get('stage') or ''))}</span>
          </div>
          <div class="d-flex flex-wrap gap-2 mt-3">
            <a class="btn btn-outline-dark" href="{escape(next_path)}">返回比赛详情</a>
            <a class="btn btn-dark" href="/prediction-admin?match_id={escape(match_id)}">后台填写人工概率</a>
          </div>
        </div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">系统概率 / 人工概率</h2>
          <p class="section-copy mb-0">系统概率基于本赛季胜率、历史单局得分、个人维度数据，并参考其他赛季数据；人工概率由后台单独录入。</p>
        </div>
      </div>
      <div class="alert alert-warning fw-semibold mb-3">预测仅用于赛前参考；未录入结果的比赛不会计入历史样本。</div>
      {table_html}
    </section>
    """
    return layout("胜率预测", body, ctx, alert=alert or form_value(ctx.query, "alert").strip())


def get_prediction_admin_page(ctx: RequestContext, alert: str = "") -> str:
    if not ctx.current_user:
        return layout("胜率预测后台", '<div class="alert alert-danger">请先登录。</div>', ctx)
    data = load_validated_data()
    match_id = form_value(ctx.query, "match_id").strip()
    matches = sorted(
        data.get("matches", []),
        key=lambda item: (
            str(item.get("played_on") or ""),
            int(item.get("round") or 0),
            int(item.get("game_no") or 0),
            str(item.get("match_id") or ""),
        ),
        reverse=True,
    )
    selected_match = get_match_by_id(matches, match_id) if match_id else (matches[0] if matches else None)
    if not selected_match:
        return layout("胜率预测后台", '<div class="alert alert-secondary">当前还没有比赛可以维护预测。</div>', ctx)
    selected_match_id = str(selected_match.get("match_id") or "")
    competition_name = get_match_competition_name(selected_match)
    if not can_manage_matches(ctx.current_user, data, competition_name):
        return layout("胜率预测后台", '<div class="alert alert-danger">你没有权限维护这场比赛的预测。</div>', ctx)
    season_name = str(selected_match.get("season") or "").strip()
    context, error = _build_match_prediction_context(ctx, selected_match_id)
    if not context:
        return layout("胜率预测后台", f'<div class="alert alert-danger">{escape(error)}</div>', ctx)
    predictions = context["predictions"]
    match_options = "".join(
        f'<option value="{escape(str(item.get("match_id") or ""))}"{" selected" if str(item.get("match_id") or "") == selected_match_id else ""}>{escape(str(item.get("played_on") or ""))} · {escape(get_match_competition_name(item))} · {escape(str(item.get("season") or ""))} · {escape(str(item.get("match_id") or ""))}</option>'
        for item in matches[:300]
    )
    headers = "".join(f"<th>{escape(label)} (%)</th>" for _, label, _, _ in PREDICTION_BUCKETS)
    rows = []
    for item in predictions:
        manual_by_key = {entry["key"]: entry for entry in item.get("manual_probabilities", [])}
        inputs = "".join(
            f'<td><input class="form-control form-control-sm" type="number" min="0" max="100" step="0.1" name="{escape(item["player_id"])}__{escape(key)}" value="{escape(_format_manual_input_value(manual_by_key.get(key, {}).get("value")))}"></td>'
            for key, _, _, _ in PREDICTION_BUCKETS
        )
        rows.append(
            f"""
            <tr>
              <td>{escape(str(item.get('seat') or ''))}</td>
              <td>{escape(item.get('player_name') or '')}</td>
              <td>{escape(item.get('team_name') or '')}</td>
              <td>{escape(item.get('expected_points') or '')}</td>
              {inputs}
            </tr>
            """
        )
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">Prediction Admin</div>
      <h1 class="display-6 fw-semibold mb-3">胜率预测后台</h1>
      <p class="mb-0 opacity-75">这里单独维护人工计算概率。保存后，前台预测页会同时展示系统概率和人工概率。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <form method="get" action="/prediction-admin" class="row g-3 align-items-end">
        <div class="col-12 col-lg-8">
          <label class="form-label">选择比赛</label>
          <select class="form-select" name="match_id">{match_options}</select>
        </div>
        <div class="col-12 col-lg-4">
          <button class="btn btn-dark w-100" type="submit">切换比赛</button>
        </div>
      </form>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">{escape(selected_match_id)} 人工概率</h2>
          <p class="section-copy mb-0">{escape(competition_name)} · {escape(season_name)}。请填写 0-100 的百分比，留空表示前台显示“未填写”。</p>
        </div>
        <a class="btn btn-outline-dark" href="/matches/{escape(selected_match_id)}/predictions">查看前台预测页</a>
      </div>
      <form method="post" action="/prediction-admin?match_id={escape(selected_match_id)}">
        <input type="hidden" name="match_id" value="{escape(selected_match_id)}">
        <div class="table-responsive">
          <table class="table align-middle">
            <thead><tr><th>座位</th><th>队员</th><th>战队</th><th>系统预测均分</th>{headers}</tr></thead>
            <tbody>{''.join(rows) or '<tr><td colspan="10" class="text-secondary">请先录入这场比赛的参赛选手名单。</td></tr>'}</tbody>
          </table>
        </div>
        <div class="d-flex flex-wrap gap-2 mt-3">
          <button class="btn btn-dark" type="submit">保存人工概率</button>
          <a class="btn btn-outline-dark" href="/prediction-admin?match_id={escape(selected_match_id)}">重置</a>
        </div>
      </form>
    </section>
    """
    return layout("胜率预测后台", body, ctx, alert=alert or form_value(ctx.query, "alert").strip())


def handle_prediction_admin(ctx: RequestContext, start_response):
    if not ctx.current_user:
        return legacy.redirect(start_response, "/login?next=/prediction-admin")
    if ctx.method == "GET":
        return legacy.start_response_html(start_response, "200 OK", get_prediction_admin_page(ctx))
    data = load_validated_data()
    match_id = form_value(ctx.form, "match_id").strip() or form_value(ctx.query, "match_id").strip()
    match = get_match_by_id(data.get("matches", []), match_id)
    if not match:
        return legacy.start_response_html(start_response, "200 OK", get_prediction_admin_page(ctx, "没有找到对应的比赛。"))
    competition_name = get_match_competition_name(match)
    if not can_manage_matches(ctx.current_user, data, competition_name):
        return legacy.start_response_html(start_response, "403 Forbidden", get_prediction_admin_page(ctx, "你没有权限维护这场比赛的预测。"))
    all_manual = load_manual_score_predictions()
    next_match_values: dict[str, dict[str, float | None]] = {}
    for participant in match.get("players", []):
        player_id = str(participant.get("player_id") or "").strip()
        if not player_id:
            continue
        values: dict[str, float | None] = {}
        for key, _, _, _ in PREDICTION_BUCKETS:
            raw_value = form_value(ctx.form, f"{player_id}__{key}").strip()
            if raw_value == "":
                values[key] = None
                continue
            try:
                values[key] = float(raw_value)
            except ValueError:
                return legacy.start_response_html(
                    start_response,
                    "200 OK",
                    get_prediction_admin_page(ctx, "人工概率只能填写 0-100 的数字。"),
                )
        normalized = normalize_manual_prediction(values)
        if any(value is not None for value in normalized.values()):
            next_match_values[player_id] = normalized
    if next_match_values:
        all_manual[match_id] = next_match_values
    else:
        all_manual.pop(match_id, None)
    save_manual_score_predictions(all_manual)
    return legacy.redirect(start_response, f"/prediction-admin?match_id={quote(match_id)}&alert={quote('人工概率已保存。')}")


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
        has_player_profile = bool(player)
        team_scores[team_id] = team_scores.get(team_id, 0.0) + float(participant.get("points_earned") or 0)
        participant_by_id[player_id] = participant
        breakdown = normalize_score_breakdown(participant) if show_score_breakdown else {}
        participants.append(
            {
                "seat": participant.get("seat") or 0,
                "player_id": player_id,
                "player_name": player.get("display_name") or player_id,
                "player_href": build_scoped_path(f"/players/{player_id}", competition_name, season_name, selected_region, selected_series_slug) if has_player_profile else "",
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
            "href": build_scoped_path(f"/players/{player_id}", competition_name, season_name, selected_region, selected_series_slug) if player_id and player else "",
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
    predictions = build_match_score_predictions(
        data,
        match,
        competition_name,
        season_name,
        selected_region,
        selected_series_slug,
    )

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
        "actions": {
            "next_href": next_path,
            "edit_href": edit_href,
            "legacy_href": legacy_href,
            "prediction_href": f"/matches/{quote(match_id)}/predictions?next={quote(build_scoped_path('/matches/' + match_id, competition_name, season_name))}",
            "admin_href": f"/prediction-admin?match_id={quote(match_id)}" if can_manage_matches(ctx.current_user, data, competition_name) else "",
        },
        "metrics": [
            {"label": "房间", "value": match.get("table_label") or "-", "copy": match.get("format") or "未记录板型"},
            {"label": "时长", "value": f"{match.get('duration_minutes') or 0} 分钟", "copy": "完整比赛耗时"},
            {"label": "胜利阵营", "value": to_chinese_camp(match.get("winning_camp") or ""), "copy": "本局最终结果"},
            {"label": "参赛分组", "value": match.get("group_label") or "未设置", "copy": "本场所属分组"},
        ],
        "awards": awards,
        "team_scores": scores,
        "score_predictions": predictions,
        "prediction_buckets": [{"key": key, "label": label} for key, label, _, _ in PREDICTION_BUCKETS],
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
