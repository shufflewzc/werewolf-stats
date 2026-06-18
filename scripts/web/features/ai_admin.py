from __future__ import annotations

from html import escape

import web_app as legacy

RequestContext = legacy.RequestContext
form_value = legacy.form_value
layout = legacy.layout
cleanup_expired_logs = legacy.cleanup_expired_logs
audit_action = legacy.audit_action
load_access_overview = legacy.load_access_overview
load_operational_overview = legacy.load_operational_overview
load_audit_logs = legacy.load_audit_logs
load_log_cleanup_state = legacy.load_log_cleanup_state
load_request_trace = legacy.load_request_trace
load_ai_conversations = legacy.load_ai_conversations
load_ai_daily_brief_settings = legacy.load_ai_daily_brief_settings
load_ai_jobs = legacy.load_ai_jobs
load_ai_prompt_templates = legacy.load_ai_prompt_templates
mask_api_key = legacy.mask_api_key
save_ai_daily_brief_settings = legacy.save_ai_daily_brief_settings
save_ai_prompt_templates = legacy.save_ai_prompt_templates
start_response_html = legacy.start_response_html

AI_JOB_TYPE_LABELS = {
    "match_day_report": "比赛日报",
    "match_day_report_pipeline": "比赛日报 Pipeline",
    "season_summary": "赛季总结",
    "data_analysis_question": "数据问答",
    "team_season_summary": "战队赛季总结",
    "player_season_summary": "选手赛季总结",
}

AI_JOB_STATUS_LABELS = {
    "running": "生成中",
    "succeeded": "已完成",
    "failed": "失败",
}


def _ai_job_status_chip(status: str) -> str:
    normalized = str(status or "").strip()
    label = AI_JOB_STATUS_LABELS.get(normalized, normalized or "未知")
    class_name = "chip"
    if normalized == "failed":
        class_name += " text-bg-danger border-0"
    elif normalized == "succeeded":
        class_name += " text-bg-success border-0"
    return f'<span class="{class_name}">{escape(label)}</span>'


def _stat_card(label: str, value: str, copy: str = "") -> str:
    return f"""
    <div class="col-12 col-md-4">
      <div class="form-panel h-100 p-3 p-lg-4">
        <div class="eyebrow mb-2">{escape(label)}</div>
        <div class="display-6 fw-semibold">{escape(value)}</div>
        {f'<div class="small text-secondary mt-2">{escape(copy)}</div>' if copy else ''}
      </div>
    </div>
    """


def _retention_days_from_env(name: str, default: int) -> int:
    try:
        return max(1, int(str(legacy.os.getenv(name, str(default))).strip() or default))
    except ValueError:
        return default


def _format_access_path(row: dict) -> str:
    query_string = str(row.get("query_string") or "").strip()
    full_path = str(row.get("path") or "/")
    if query_string:
        full_path += "?" + query_string
    return full_path


def _status_group(status_code: int) -> str:
    if status_code <= 0:
        return "unknown"
    if status_code >= 500:
        return "5xx"
    if status_code >= 400:
        return "4xx"
    if status_code >= 300:
        return "3xx"
    if status_code >= 200:
        return "2xx"
    return "other"


def _status_chip(status_code: int) -> str:
    if status_code <= 0:
        return '<span class="chip">未记录</span>'
    class_name = "chip"
    if status_code >= 500:
        class_name += " text-bg-danger border-0"
    elif status_code >= 400:
        class_name += " text-bg-warning border-0"
    elif status_code < 300:
        class_name += " text-bg-success border-0"
    return f'<span class="{class_name}">{status_code}</span>'


def _duration_text(duration_ms: int) -> str:
    if duration_ms <= 0:
        return "未记录"
    if duration_ms >= 1000:
        return f"{duration_ms / 1000:.2f}s"
    return f"{duration_ms}ms"


def _format_rate(value: float) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def _request_trace_href(request_id: str) -> str:
    value = str(request_id or "").strip()
    if not value:
        return ""
    return "/request-trace?request_id=" + legacy.quote(value)


def _copy_request_id_control(request_id: str, *, class_name: str = "btn btn-sm btn-outline-dark") -> str:
    value = str(request_id or "").strip()
    if not value:
        return f'<button class="{class_name}" type="button" disabled><code>未记录</code></button>'
    return (
        f'<button class="{class_name}" type="button" data-copy-text="{escape(value)}" title="复制请求编号">'
        f'<code>{escape(value)}</code></button>'
    )


def _trace_request_link(request_id: str) -> str:
    href = _request_trace_href(request_id)
    if not href:
        return ""
    return f'<a class="btn btn-sm btn-outline-dark mt-1" href="{escape(href)}">排查</a>'


def _render_access_log_rows(rows: list[dict], *, empty_text: str, row_limit: int = 300, filterable: bool = False) -> str:
    rendered_rows = []
    for row in rows[:row_limit]:
        full_path = _format_access_path(row)
        status_code = int(row.get("status_code") or 0)
        duration_ms = int(row.get("duration_ms") or 0)
        username = str(row.get("username") or "访客").strip() or "访客"
        request_id = str(row.get("request_id") or "").strip()
        method = str(row.get("method") or "").strip().upper()
        ip_address = str(row.get("ip_address") or "").strip()
        user_agent = str(row.get("user_agent") or "").strip()
        keyword_text = " ".join(
            [
                str(row.get("created_at") or ""),
                method,
                str(status_code or ""),
                full_path,
                username,
                ip_address,
                user_agent,
                request_id,
            ]
        ).lower()
        filter_attrs = (
            f'data-access-row data-access-keyword="{escape(keyword_text)}" '
            f'data-access-method="{escape(method)}" data-access-status-group="{escape(_status_group(status_code))}"'
            if filterable
            else ""
        )
        rendered_rows.append(
            f"""
            <tr {filter_attrs}>
              <td class="text-secondary">{escape(row.get('created_at') or '')}</td>
              <td>{escape(method)}</td>
              <td>{_status_chip(status_code)}</td>
              <td class="text-nowrap">{escape(_duration_text(duration_ms))}</td>
              <td class="text-break"><code>{escape(full_path)}</code></td>
              <td>{escape(username)}</td>
              <td class="text-break small text-secondary">{escape(ip_address)}</td>
              <td class="text-break small text-secondary">
                {_copy_request_id_control(request_id)}
                {_trace_request_link(request_id)}
                <div class="mt-1">{escape(user_agent)}</div>
              </td>
            </tr>
            """
        )
    return "".join(rendered_rows) if rendered_rows else f'<tr><td colspan="8" class="text-secondary">{escape(empty_text)}</td></tr>'


def _render_api_path_rows(rows: list[dict]) -> str:
    rendered_rows = []
    for row in rows:
        rendered_rows.append(
            f"""
            <tr>
              <td class="text-break"><code>{escape(row.get('path') or '')}</code></td>
              <td>{escape(str(row.get('visits') or 0))}</td>
              <td>{escape(_duration_text(int(float(row.get('avg_duration_ms') or 0))))}</td>
              <td>{escape(_duration_text(int(row.get('max_duration_ms') or 0)))}</td>
              <td>{escape(str(row.get('error_count') or 0))}</td>
              <td>{escape(str(row.get('slow_count') or 0))}</td>
              <td class="text-secondary">{escape(row.get('last_seen_at') or '')}</td>
            </tr>
            """
        )
    return "".join(rendered_rows) if rendered_rows else '<tr><td colspan="7" class="text-secondary">暂无 API 访问记录。</td></tr>'


def _ops_health_status(
    *,
    error_rate: float,
    slow_rate: float,
    cache_metrics: dict,
    schema_error: str = "",
) -> dict[str, object]:
    issues: list[dict[str, str]] = []
    score = 100
    if schema_error:
        score -= 45
        issues.append({"level": "danger", "title": "访问日志不可读", "copy": "运维总览无法读取访问日志，请先检查数据库结构。"})
    if error_rate >= 0.05:
        score -= 35
        issues.append({"level": "danger", "title": "API 错误率过高", "copy": f"当前错误率 {_format_rate(error_rate)}，需要优先排查 4xx/5xx。"})
    elif error_rate >= 0.02:
        score -= 18
        issues.append({"level": "warning", "title": "API 错误率偏高", "copy": f"当前错误率 {_format_rate(error_rate)}，建议查看近期问题请求。"})
    if slow_rate >= 0.10:
        score -= 30
        issues.append({"level": "danger", "title": "API 慢请求过多", "copy": f"当前慢请求率 {_format_rate(slow_rate)}，建议优先看最慢 API。"})
    elif slow_rate >= 0.05:
        score -= 15
        issues.append({"level": "warning", "title": "API 慢请求偏多", "copy": f"当前慢请求率 {_format_rate(slow_rate)}，需要持续观察。"})
    cache_reads = int(cache_metrics.get("hits") or 0) + int(cache_metrics.get("misses") or 0)
    cache_hit_rate = float(cache_metrics.get("hit_rate") or 0.0)
    if cache_metrics.get("enabled") and cache_reads >= 10 and cache_hit_rate < 0.50:
        score -= 10
        issues.append({"level": "warning", "title": "预测缓存命中率偏低", "copy": f"当前命中率 {_format_rate(cache_hit_rate)}，可能存在频繁失效或请求条件过散。"})
    if not cache_metrics.get("enabled"):
        score -= 8
        issues.append({"level": "warning", "title": "预测缓存已关闭", "copy": "胜率预测会直接走实时计算，建议只在排障时关闭。"})
    score = max(0, min(100, score))
    if score >= 90:
        label = "健康"
        level = "success"
        summary = "核心 API 状态稳定。"
    elif score >= 70:
        label = "关注"
        level = "warning"
        summary = "服务可用，但已有指标需要关注。"
    else:
        label = "异常"
        level = "danger"
        summary = "存在明显风险，建议优先处理告警项。"
    if not issues:
        issues.append({"level": "success", "title": "暂无告警", "copy": "错误率、慢请求率和预测缓存状态都在阈值内。"})
    return {
        "score": score,
        "label": label,
        "level": level,
        "summary": summary,
        "issues": issues,
    }


def _render_ops_issue_rows(issues: list[dict[str, str]]) -> str:
    class_by_level = {
        "success": "text-bg-success",
        "warning": "text-bg-warning",
        "danger": "text-bg-danger",
    }
    rendered = []
    for issue in issues:
        level = issue.get("level") or "warning"
        rendered.append(
            f"""
            <div class="form-panel p-3">
              <span class="chip {class_by_level.get(level, 'text-bg-warning')} border-0">{escape(issue.get('title') or '')}</span>
              <div class="small text-secondary mt-2">{escape(issue.get('copy') or '')}</div>
            </div>
            """
        )
    return "".join(rendered)


def build_ops_payload() -> dict:
    schema_error = ""
    try:
        overview = load_operational_overview(120)
    except Exception as exc:
        overview = {
            "api_total": 0,
            "api_today": 0,
            "api_error_count": 0,
            "api_slow_count": 0,
            "api_avg_duration_ms": 0,
            "api_max_duration_ms": 0,
            "api_paths": [],
            "recent_api_logs": [],
            "recent_problem_logs": [],
        }
        schema_error = str(exc)
    cache_metrics = legacy.get_prediction_api_cache_metrics()
    api_total = max(1, int(overview.get("api_total") or 0))
    error_rate = int(overview.get("api_error_count") or 0) / api_total
    slow_rate = int(overview.get("api_slow_count") or 0) / api_total
    health = _ops_health_status(
        error_rate=error_rate,
        slow_rate=slow_rate,
        cache_metrics=cache_metrics,
        schema_error=schema_error,
    )
    return {
        "ok": not schema_error and str(health.get("level") or "") != "danger",
        "health": health,
        "rates": {
            "error_rate": error_rate,
            "slow_rate": slow_rate,
        },
        "overview": overview,
        "prediction_cache": cache_metrics,
        "schema_error": schema_error,
    }


def get_ops_page(ctx: RequestContext, alert: str = "") -> str:
    payload = build_ops_payload()
    overview = payload["overview"]
    cache_metrics = payload["prediction_cache"]
    error_rate = float(payload["rates"]["error_rate"])
    slow_rate = float(payload["rates"]["slow_rate"])
    health = payload["health"]
    schema_error = str(payload.get("schema_error") or "")
    cache_status = "已开启" if cache_metrics.get("enabled") else "已关闭"
    api_path_rows = _render_api_path_rows(overview.get("api_paths", []))
    problem_rows = _render_access_log_rows(
        overview.get("recent_problem_logs", []),
        empty_text="暂无慢请求或错误请求。",
        row_limit=12,
    )
    recent_rows = _render_access_log_rows(
        overview.get("recent_api_logs", []),
        empty_text="暂无 API 请求记录。",
        row_limit=40,
    )
    schema_alert = (
        f'<div class="alert alert-warning">运维总览暂时无法读取访问日志：{escape(schema_error)}</div>'
        if schema_error
        else ""
    )
    health_class = {
        "success": "text-bg-success",
        "warning": "text-bg-warning",
        "danger": "text-bg-danger",
    }.get(str(health.get("level") or ""), "text-bg-warning")
    issue_rows = _render_ops_issue_rows(list(health.get("issues") or []))
    body = f"""
    <section class="section-card">
      <div class="d-flex flex-wrap justify-content-between align-items-start gap-3">
        <div>
          <p class="eyebrow mb-2">Operations</p>
          <h1 class="page-title mb-2">运维总览</h1>
          <p class="section-copy mb-0">集中查看小程序 API 耗时、错误请求和预测缓存状态。</p>
          <div class="d-flex flex-wrap align-items-center gap-2 mt-3">
            <span class="chip {health_class} border-0">健康评分 {escape(str(health.get('score')))} · {escape(str(health.get('label')))}</span>
            <span class="small text-secondary">{escape(str(health.get('summary') or ''))}</span>
          </div>
        </div>
        <div class="d-flex flex-wrap gap-2">
          <a class="btn btn-outline-dark" href="/access-stats">访问统计</a>
          <a class="btn btn-outline-dark" href="/request-trace">请求排障</a>
        </div>
      </div>
      {schema_alert}
    </section>

    <section class="section-card">
      <div class="section-heading">
        <div>
          <p class="eyebrow mb-2">Alerts</p>
          <h2>健康告警</h2>
          <p class="section-copy mb-0">阈值：错误率 2% 提醒、5% 异常；慢请求率 5% 提醒、10% 异常。</p>
        </div>
      </div>
      <div class="row g-3">
        <div class="col-12 col-lg-4">
          <div class="form-panel h-100 p-3 p-lg-4">
            <div class="eyebrow mb-2">健康评分</div>
            <div class="display-6 fw-semibold">{escape(str(health.get("score")))}</div>
            <div class="small text-secondary mt-2">{escape(str(health.get("summary") or ""))}</div>
          </div>
        </div>
        <div class="col-12 col-lg-8">
          <div class="row g-3">{issue_rows}</div>
        </div>
      </div>
    </section>

    <section class="row g-3">
      {_stat_card("今日 API 请求", str(overview.get("api_today") or 0), "当天小程序和前端 API 调用次数。")}
      {_stat_card("API 错误率", _format_rate(error_rate), f"错误请求 {overview.get('api_error_count') or 0} 次。")}
      {_stat_card("API 慢请求率", _format_rate(slow_rate), f"慢请求 {overview.get('api_slow_count') or 0} 次，阈值 1000ms。")}
      {_stat_card("API 平均耗时", _duration_text(int(overview.get("api_avg_duration_ms") or 0)), f"最大耗时 {_duration_text(int(overview.get('api_max_duration_ms') or 0))}。")}
      {_stat_card("预测缓存", cache_status, f"{cache_metrics.get('entries') or 0}/{cache_metrics.get('max_entries') or 0} 条，TTL {cache_metrics.get('ttl_seconds') or 0}s。")}
      {_stat_card("预测缓存命中率", _format_rate(float(cache_metrics.get("hit_rate") or 0.0)), f"命中 {cache_metrics.get('hits') or 0}，未命中 {cache_metrics.get('misses') or 0}。")}
    </section>

    <section class="section-card">
      <div class="section-heading">
        <div>
          <p class="eyebrow mb-2">Latency</p>
          <h2>最慢 API</h2>
          <p class="section-copy mb-0">按历史最大耗时排序，优先关注 `max` 和错误数。</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle mb-0">
          <thead><tr><th>接口</th><th>请求数</th><th>平均</th><th>最大</th><th>错误</th><th>慢请求</th><th>最近访问</th></tr></thead>
          <tbody>{api_path_rows}</tbody>
        </table>
      </div>
    </section>

    <section class="section-card">
      <div class="section-heading">
        <div>
          <p class="eyebrow mb-2">Problems</p>
          <h2>近期问题请求</h2>
          <p class="section-copy mb-0">包含 4xx/5xx 与超过 1000ms 的 API 请求，可直接复制请求编号排查。</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle mb-0">
          <thead><tr><th>时间</th><th>方式</th><th>状态</th><th>耗时</th><th>页面</th><th>用户</th><th>IP</th><th>请求/User Agent</th></tr></thead>
          <tbody>{problem_rows}</tbody>
        </table>
      </div>
    </section>

    <section class="section-card">
      <div class="section-heading">
        <div>
          <p class="eyebrow mb-2">Recent</p>
          <h2>近期 API 请求</h2>
          <p class="section-copy mb-0">用于观察小程序真实访问路径和接口响应状态。</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle mb-0">
          <thead><tr><th>时间</th><th>方式</th><th>状态</th><th>耗时</th><th>页面</th><th>用户</th><th>IP</th><th>请求/User Agent</th></tr></thead>
          <tbody>{recent_rows}</tbody>
        </table>
      </div>
    </section>
    <script>
      (function () {{
        document.querySelectorAll("[data-copy-text]").forEach((button) => {{
          button.addEventListener("click", function () {{
            const value = button.getAttribute("data-copy-text") || "";
            if (!value) return;
            if (navigator.clipboard && navigator.clipboard.writeText) {{
              navigator.clipboard.writeText(value).catch(function () {{}});
            }}
          }});
        }});
      }})();
    </script>
    """
    return layout("运维总览", body, ctx, alert=alert)


def get_access_stats_page(ctx: RequestContext, alert: str = "") -> str:
    schema_error = ""
    try:
        overview = load_access_overview(200)
    except Exception as exc:
        overview = {
            "total_visits": 0,
            "today_visits": 0,
            "unique_ip_count": 0,
            "error_count": 0,
            "slow_count": 0,
            "avg_duration_ms": 0,
            "max_duration_ms": 0,
            "status_counts": [],
            "top_paths": [],
            "slow_logs": [],
            "error_logs": [],
            "recent_logs": [],
        }
        schema_error = str(exc)
    cleanup_state = load_log_cleanup_state()
    access_retention_days = _retention_days_from_env("ACCESS_LOG_RETENTION_DAYS", 30)
    audit_retention_days = _retention_days_from_env("AUDIT_LOG_RETENTION_DAYS", 365)
    last_cleanup_text = (
        f"{cleanup_state.get('ran_at', '')}，访问日志 {cleanup_state.get('deleted_access_logs', 0)} 条，审计日志 {cleanup_state.get('deleted_audit_logs', 0)} 条"
        if cleanup_state
        else "尚未记录清理结果"
    )
    recent_logs = overview.get("recent_logs", [])
    method_options = sorted(
        {
            str(row.get("method") or "").strip().upper()
            for row in recent_logs
            if str(row.get("method") or "").strip()
        }
    )
    status_rows = []
    for row in overview.get("status_counts", []):
        status_code = int(row.get("status_code") or 0)
        status_rows.append(
            f"""
            <tr>
              <td>{_status_chip(status_code)}</td>
              <td>{escape(_status_group(status_code))}</td>
              <td>{escape(str(row.get('count') or 0))}</td>
            </tr>
            """
        )
    top_path_rows = []
    for row in overview.get("top_paths", []):
        top_path_rows.append(
            f"""
            <tr>
              <td class="text-break"><code>{escape(row.get('path') or '/')}</code></td>
              <td>{escape(str(row.get('visits') or 0))}</td>
              <td class="text-secondary">{escape(row.get('last_seen_at') or '')}</td>
            </tr>
            """
        )
    slow_rows = _render_access_log_rows(overview.get("slow_logs", []), empty_text="暂无慢请求记录。", row_limit=10)
    error_rows = _render_access_log_rows(overview.get("error_logs", []), empty_text="暂无错误请求记录。", row_limit=10)
    recent_rows = _render_access_log_rows(recent_logs, empty_text="暂无访问记录。", filterable=True)
    cleanup_preview = getattr(ctx, "cleanup_preview", None)
    cleanup_preview_html = ""
    if isinstance(cleanup_preview, dict):
        cleanup_preview_html = f"""
        <div class="alert alert-warning mt-3 mb-0">
          <div class="fw-semibold mb-2">清理预览</div>
          <div>访问日志将清理 {escape(str(cleanup_preview.get('deleted_access_logs') or 0))} 条，截止日期 {escape(str(cleanup_preview.get('access_cutoff_date') or ''))}。</div>
          <div>审计日志将清理 {escape(str(cleanup_preview.get('deleted_audit_logs') or 0))} 条，截止日期 {escape(str(cleanup_preview.get('audit_cutoff_date') or ''))}。</div>
          <form method="post" action="/access-stats" class="row g-2 align-items-end mt-3">
            <input type="hidden" name="action" value="cleanup_logs_confirm">
            <input type="hidden" name="access_retention_days" value="{escape(str(cleanup_preview.get('access_retention_days') or access_retention_days))}">
            <input type="hidden" name="audit_retention_days" value="{escape(str(cleanup_preview.get('audit_retention_days') or audit_retention_days))}">
            <div class="col-12 col-xl-8">
              <label class="form-label">确认执行</label>
              <input class="form-control" name="danger_confirmation" placeholder="输入 清理日志 确认">
            </div>
            <div class="col-12 col-xl-4">
              <button class="btn btn-outline-danger w-100" type="submit">确认清理这些日志</button>
            </div>
          </form>
        </div>
        """
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">运营统计</div>
      <h1 class="display-6 fw-semibold mb-3">访问统计</h1>
      <p class="mb-0 opacity-75">记录站内请求、状态码、耗时、登录用户、来源 IP 和请求编号，静态资源不计入。</p>
    </section>
    {f'<div class="alert alert-warning">访问统计表结构还没有在当前数据库中更新。请先执行 PostgreSQL 表结构更新脚本后再查看访问统计。错误信息：{escape(schema_error)}</div>' if schema_error else ''}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-3">
        {_stat_card("累计访问", str(overview.get("total_visits") or 0), "数据库中保存的全部访问记录")}
        {_stat_card("今日访问", str(overview.get("today_visits") or 0), "按北京时间自然日统计")}
        {_stat_card("独立 IP", str(overview.get("unique_ip_count") or 0), "累计出现过的访问 IP 数")}
        {_stat_card("错误请求", str(overview.get("error_count") or 0), "状态码大于等于 400 的请求")}
        {_stat_card("慢请求", str(overview.get("slow_count") or 0), "耗时大于等于 1000ms 的请求")}
        {_stat_card("平均耗时", _duration_text(int(overview.get("avg_duration_ms") or 0)), f"最高 {_duration_text(int(overview.get('max_duration_ms') or 0))}")}
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">日志留存</h2>
          <p class="section-copy mb-0">访问日志默认保留 {access_retention_days} 天，审计日志默认保留 {audit_retention_days} 天。上次清理：{escape(last_cleanup_text)}</p>
        </div>
      </div>
      <form method="post" action="/access-stats" class="form-panel p-3">
        <input type="hidden" name="action" value="cleanup_logs_preview">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-md-4">
            <label class="form-label">访问日志保留天数</label>
            <input class="form-control" name="access_retention_days" type="number" min="1" max="3650" value="{access_retention_days}">
          </div>
          <div class="col-12 col-md-4">
            <label class="form-label">审计日志保留天数</label>
            <input class="form-control" name="audit_retention_days" type="number" min="1" max="3650" value="{audit_retention_days}">
          </div>
          <div class="col-12 col-md-4">
            <button class="btn btn-outline-dark w-100" type="submit">预览过期日志</button>
          </div>
        </div>
        {cleanup_preview_html}
      </form>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-4">
        <div class="col-12 col-xl-7">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">热门页面</h2>
              <p class="section-copy mb-0">按访问次数排序，辅助判断用户主要看哪些页面。</p>
            </div>
          </div>
          <div class="table-responsive">
            <table class="table align-middle mb-0">
              <thead><tr><th>页面</th><th>访问</th><th>最近访问</th></tr></thead>
              <tbody>{''.join(top_path_rows) if top_path_rows else '<tr><td colspan="3" class="text-secondary">暂无访问记录。</td></tr>'}</tbody>
            </table>
          </div>
        </div>
        <div class="col-12 col-xl-5">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">状态分布</h2>
              <p class="section-copy mb-0">用于快速判断错误请求占比。</p>
            </div>
          </div>
          <div class="table-responsive">
            <table class="table align-middle mb-0">
              <thead><tr><th>状态码</th><th>分组</th><th>次数</th></tr></thead>
              <tbody>{''.join(status_rows) if status_rows else '<tr><td colspan="3" class="text-secondary">暂无状态记录。</td></tr>'}</tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-4">
        <div class="col-12 col-xl-6">
          <h2 class="section-title mb-2">最近错误请求</h2>
          <p class="section-copy mb-3">优先排查 4xx/5xx，结合请求编号查看服务器日志。</p>
          <div class="table-responsive">
            <table class="table align-middle mb-0">
              <thead><tr><th>时间</th><th>方式</th><th>状态</th><th>耗时</th><th>页面</th><th>用户</th><th>IP</th><th>请求/User Agent</th></tr></thead>
              <tbody>{error_rows}</tbody>
            </table>
          </div>
        </div>
        <div class="col-12 col-xl-6">
          <h2 class="section-title mb-2">最慢请求</h2>
          <p class="section-copy mb-3">按耗时倒序展示最近记录中的高耗时请求。</p>
          <div class="table-responsive">
            <table class="table align-middle mb-0">
              <thead><tr><th>时间</th><th>方式</th><th>状态</th><th>耗时</th><th>页面</th><th>用户</th><th>IP</th><th>请求/User Agent</th></tr></thead>
              <tbody>{slow_rows}</tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">最近访问</h2>
          <p class="section-copy mb-0">显示最近 200 条访问记录，可按路径、用户、IP、请求编号、状态码筛选。</p>
        </div>
        <div class="d-flex flex-wrap gap-2">
          <a class="btn btn-outline-dark" href="/audit-logs">查看操作审计</a>
          <a class="btn btn-outline-dark" href="/request-trace">请求编号排障</a>
          <a class="btn btn-outline-dark" href="/accounts">返回账号管理</a>
        </div>
      </div>
      <div class="form-panel p-3 mb-3">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-xl-4">
            <label class="form-label">搜索</label>
            <input class="form-control" id="access-search" placeholder="路径、账号、IP、状态码、请求编号">
          </div>
          <div class="col-12 col-md-4 col-xl-2">
            <label class="form-label">方式</label>
            <select class="form-select" id="access-method-filter">
              <option value="">全部方式</option>
              {''.join(f'<option value="{escape(method)}">{escape(method)}</option>' for method in method_options)}
            </select>
          </div>
          <div class="col-12 col-md-4 col-xl-3">
            <label class="form-label">状态</label>
            <select class="form-select" id="access-status-filter">
              <option value="">全部状态</option>
              <option value="2xx">2xx 成功</option>
              <option value="3xx">3xx 跳转</option>
              <option value="4xx">4xx 客户端错误</option>
              <option value="5xx">5xx 服务错误</option>
              <option value="unknown">未记录</option>
            </select>
          </div>
          <div class="col-12 col-md-4 col-xl-3">
            <button class="btn btn-outline-dark w-100" type="button" id="access-filter-reset">重置</button>
          </div>
        </div>
        <div class="small text-secondary mt-2"><span id="access-visible-count">{len(recent_logs)}</span> / {len(recent_logs)} 条记录</div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle mb-0">
          <thead><tr><th>时间</th><th>方式</th><th>状态</th><th>耗时</th><th>页面</th><th>用户</th><th>IP</th><th>请求/User Agent</th></tr></thead>
          <tbody>
            {recent_rows}
            <tr id="access-empty-row" class="d-none"><td colspan="8" class="text-secondary">没有符合筛选条件的访问记录。</td></tr>
          </tbody>
        </table>
      </div>
    </section>
    <script>
      (function () {{
        const searchInput = document.getElementById("access-search");
        const methodFilter = document.getElementById("access-method-filter");
        const statusFilter = document.getElementById("access-status-filter");
        const resetButton = document.getElementById("access-filter-reset");
        const visibleCount = document.getElementById("access-visible-count");
        const emptyRow = document.getElementById("access-empty-row");
        const rows = Array.from(document.querySelectorAll("[data-access-row]"));

        function applyFilters() {{
          const keyword = (searchInput && searchInput.value || "").trim().toLowerCase();
          const method = methodFilter && methodFilter.value || "";
          const statusGroup = statusFilter && statusFilter.value || "";
          let shown = 0;
          rows.forEach((row) => {{
            const matchesKeyword = !keyword || (row.getAttribute("data-access-keyword") || "").includes(keyword);
            const matchesMethod = !method || row.getAttribute("data-access-method") === method;
            const matchesStatus = !statusGroup || row.getAttribute("data-access-status-group") === statusGroup;
            const visible = matchesKeyword && matchesMethod && matchesStatus;
            row.classList.toggle("d-none", !visible);
            if (visible) shown += 1;
          }});
          if (visibleCount) visibleCount.textContent = String(shown);
          if (emptyRow) emptyRow.classList.toggle("d-none", shown !== 0 || rows.length === 0);
        }}

        [searchInput, methodFilter, statusFilter].forEach((control) => {{
          if (control) control.addEventListener("input", applyFilters);
          if (control) control.addEventListener("change", applyFilters);
        }});
        if (resetButton) {{
          resetButton.addEventListener("click", function () {{
            if (searchInput) searchInput.value = "";
            if (methodFilter) methodFilter.value = "";
            if (statusFilter) statusFilter.value = "";
            applyFilters();
          }});
        }}
        document.querySelectorAll("[data-copy-text]").forEach((button) => {{
          button.addEventListener("click", function () {{
            const value = button.getAttribute("data-copy-text") || "";
            if (!value) return;
            if (navigator.clipboard && navigator.clipboard.writeText) {{
              navigator.clipboard.writeText(value).catch(function () {{}});
            }}
          }});
        }});
        applyFilters();
      }})();
    </script>
    """
    return layout("访问统计", body, ctx, alert=alert)


def handle_access_stats(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_access_stats_page(ctx))
    if ctx.method != "POST":
        return start_response_html(
            start_response,
            "405 Method Not Allowed",
            layout("请求无效", '<div class="alert alert-danger">访问统计只支持查看和清理操作。</div>', ctx),
        )
    action = form_value(ctx.form, "action").strip()
    if action not in {"cleanup_logs_preview", "cleanup_logs_confirm"}:
        return start_response_html(start_response, "200 OK", get_access_stats_page(ctx, alert="未识别的操作。"))
    try:
        access_days = max(1, min(3650, int(form_value(ctx.form, "access_retention_days") or "30")))
        audit_days = max(1, min(3650, int(form_value(ctx.form, "audit_retention_days") or "365")))
    except ValueError:
        return start_response_html(start_response, "200 OK", get_access_stats_page(ctx, alert="保留天数必须是数字。"))
    if action == "cleanup_logs_confirm" and form_value(ctx.form, "danger_confirmation").strip() != "清理日志":
        try:
            preview_result = cleanup_expired_logs(
                access_retention_days=access_days,
                audit_retention_days=audit_days,
                dry_run=True,
            )
        except Exception as exc:
            return start_response_html(start_response, "200 OK", get_access_stats_page(ctx, alert=f"清理预览失败：{exc}"))
        preview_ctx = RequestContext(
            method=ctx.method,
            path=ctx.path,
            query=ctx.query,
            form=ctx.form,
            files=ctx.files,
            current_user=ctx.current_user,
            now_label=ctx.now_label,
            remote_addr=ctx.remote_addr,
            request_id=ctx.request_id,
        )
        setattr(preview_ctx, "cleanup_preview", preview_result)
        return start_response_html(
            start_response,
            "200 OK",
            get_access_stats_page(preview_ctx, alert="执行清理前，请输入确认文字：清理日志。"),
        )
    try:
        result = cleanup_expired_logs(
            access_retention_days=access_days,
            audit_retention_days=audit_days,
            dry_run=action == "cleanup_logs_preview",
        )
    except Exception as exc:
        return start_response_html(start_response, "200 OK", get_access_stats_page(ctx, alert=f"清理失败：{exc}"))
    if action == "cleanup_logs_preview":
        preview_ctx = RequestContext(
            method=ctx.method,
            path=ctx.path,
            query=ctx.query,
            form=ctx.form,
            files=ctx.files,
            current_user=ctx.current_user,
            now_label=ctx.now_label,
            remote_addr=ctx.remote_addr,
            request_id=ctx.request_id,
        )
        setattr(preview_ctx, "cleanup_preview", result)
        return start_response_html(
            start_response,
            "200 OK",
            get_access_stats_page(preview_ctx, alert="已完成清理预览，请确认后再执行。"),
        )
    audit_action(
        ctx,
        "logs.cleanup",
        target_type="logs",
        target_id="access_logs,audit_logs",
        summary=(
            f"清理过期日志：访问 {result['deleted_access_logs']} 条，"
            f"审计 {result['deleted_audit_logs']} 条"
        ),
        metadata=result,
    )
    return start_response_html(
        start_response,
        "200 OK",
        get_access_stats_page(
            ctx,
            alert=(
                "日志清理完成："
                f"访问日志 {result['deleted_access_logs']} 条，"
                f"审计日志 {result['deleted_audit_logs']} 条。"
            ),
        ),
    )


AUDIT_ACTION_LABELS = {
    "account.create": "创建账号",
    "account.update": "更新账号",
    "account.delete": "删除账号",
    "permission.update": "更新权限",
    "profile.update": "更新个人资料",
    "binding.request": "提交绑定申请",
    "binding.direct_bind": "直接绑定参赛ID",
    "binding.approve": "通过绑定申请",
    "binding.reject": "拒绝绑定申请",
    "binding.unbind": "解绑参赛ID",
    "guild.create": "创建门派",
    "guild.honors_update": "更新门派荣誉",
    "guild_join.request": "提交入门派申请",
    "guild_join.approve": "通过入门派申请",
    "guild_join.reject": "拒绝入门派申请",
    "team_claim.request": "提交战队认领",
    "team_claim.cancel": "取消战队认领",
    "team_claim.approve": "通过战队认领",
    "team_claim.reject": "拒绝战队认领",
    "team_claim.unbind": "解除战队认领",
    "team.profile_update": "更新战队资料",
    "team.stage_groups_update": "更新战队分组",
    "team.logo_update": "更新战队图标",
    "team.manual_achievements_update": "更新战队成就",
    "team.ai_summary_save": "保存战队 AI 总结",
    "team.ai_summary_generate": "生成战队 AI 总结",
    "player.profile_update": "更新选手资料",
    "player.manual_achievements_update": "更新选手成就",
    "player.ai_summary_save": "保存选手 AI 总结",
    "player.ai_summary_generate": "生成选手 AI 总结",
    "season.ai_summary_save": "保存赛季 AI 总结",
    "season.ai_summary_generate": "生成赛季 AI 总结",
    "matches.batch_score_exclusion": "批量调整抽局",
    "matches.batch_delete": "批量删除比赛",
    "matches.batch_create": "批量创建比赛",
    "matches.import_excel": "导入比赛 Excel",
    "dimension.import_excel": "导入维度数据",
    "dimension.clear": "清空维度数据",
    "dimension.delete_day": "删除单日维度",
    "logs.cleanup": "清理过期日志",
    "team_logo.import_excel": "导入门派图标",
    "player_photo.import_manual": "手动确认头像",
    "player_photo.import_zip": "导入头像 ZIP",
    "match.create": "新增比赛",
    "team.delete": "删除战队",
    "season.delete": "删除赛季",
}


def _audit_action_label(action: str) -> str:
    return AUDIT_ACTION_LABELS.get(str(action or "").strip(), str(action or "").strip() or "未知操作")


def _count_top(items: list[dict], key: str, limit: int = 8) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "").strip() or "未记录"
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]


def get_audit_logs_page(ctx: RequestContext, alert: str = "") -> str:
    schema_error = ""
    try:
        logs = load_audit_logs(200)
    except Exception as exc:
        logs = []
        schema_error = str(exc)
    action_options = []
    for action, _count in _count_top(logs, "action", limit=100):
        action_options.append(
            f'<option value="{escape(action)}">{escape(_audit_action_label(action))} · {escape(action)}</option>'
        )
    user_options = []
    for username, _count in _count_top(logs, "username", limit=100):
        if username == "未记录":
            continue
        user_options.append(
            f'<option value="{escape(username)}">{escape(username)}</option>'
        )
    action_rows = []
    for action, count in _count_top(logs, "action"):
        action_rows.append(
            f"""
            <tr>
              <td>{escape(_audit_action_label(action))}</td>
              <td><code>{escape(action)}</code></td>
              <td>{count}</td>
            </tr>
            """
        )
    user_rows = []
    for username, count in _count_top(logs, "username"):
        user_rows.append(
            f"""
            <tr>
              <td>{escape(username)}</td>
              <td>{count}</td>
            </tr>
            """
        )
    recent_rows = []
    for item in logs:
        action_code = str(item.get("action") or "").strip()
        action_label = _audit_action_label(action_code)
        username = str(item.get("username") or "未记录").strip() or "未记录"
        request_id = str(item.get("request_id") or "").strip()
        target_type = str(item.get("target_type") or "").strip()
        target_id = str(item.get("target_id") or "").strip()
        summary = str(item.get("summary") or "").strip()
        ip_address = str(item.get("ip_address") or "").strip()
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        metadata_parts = []
        for key in [
            "competition_name",
            "season_name",
            "played_on",
            "updated_count",
            "deleted_player_count",
            "deleted_team_count",
            "match_count",
        ]:
            value = metadata.get(key)
            if value not in (None, "", []):
                metadata_parts.append(f"{key}: {value}")
        metadata_text = "；".join(metadata_parts)
        keyword_text = " ".join(
            [
                str(item.get("created_at") or ""),
                username,
                action_code,
                action_label,
                summary,
                target_type,
                target_id,
                ip_address,
                request_id,
                metadata_text,
            ]
        ).lower()
        recent_rows.append(
            f"""
            <tr data-audit-row data-audit-keyword="{escape(keyword_text)}" data-audit-action="{escape(action_code)}" data-audit-username="{escape(username)}">
              <td class="text-secondary">{escape(item.get('created_at') or '')}</td>
              <td>{escape(username)}</td>
              <td>
                <div>{escape(action_label)}</div>
                <div class="small text-secondary"><code>{escape(action_code)}</code></div>
              </td>
              <td class="text-break">
                <div>{escape(summary)}</div>
                {f'<div class="small text-secondary mt-1">{escape(metadata_text)}</div>' if metadata_text else ''}
              </td>
              <td class="text-break">
                <div>{escape(target_type)}</div>
                <div class="small text-secondary"><code>{escape(target_id)}</code></div>
              </td>
              <td class="text-break small text-secondary">
                <div>{escape(ip_address)}</div>
                {_copy_request_id_control(request_id, class_name="btn btn-sm btn-outline-dark mt-1")}
                {_trace_request_link(request_id)}
              </td>
            </tr>
            """
        )
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">安全审计</div>
      <h1 class="display-6 fw-semibold mb-3">操作审计</h1>
      <p class="mb-0 opacity-75">记录后台账号、权限、赛事数据导入和批量变更等关键操作。</p>
    </section>
    {f'<div class="alert alert-warning">审计表结构还没有在当前数据库中启用。请先执行 PostgreSQL 表结构更新脚本后再查看审计记录。错误信息：{escape(schema_error)}</div>' if schema_error else ''}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-3">
        {_stat_card("最近记录", str(len(logs)), "当前显示最近 200 条审计记录")}
        {_stat_card("涉及账号", str(len({str(item.get('username') or '').strip() for item in logs if str(item.get('username') or '').strip()})), "最近记录里的操作账号数")}
        {_stat_card("动作类型", str(len({str(item.get('action') or '').strip() for item in logs if str(item.get('action') or '').strip()})), "最近记录里的操作类型数")}
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-4">
        <div class="col-12 col-xl-7">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">动作分布</h2>
              <p class="section-copy mb-0">按最近 200 条记录统计。</p>
            </div>
          </div>
          <div class="table-responsive">
            <table class="table align-middle mb-0">
              <thead><tr><th>动作</th><th>代码</th><th>次数</th></tr></thead>
              <tbody>{''.join(action_rows) if action_rows else '<tr><td colspan="3" class="text-secondary">暂无审计记录。</td></tr>'}</tbody>
            </table>
          </div>
        </div>
        <div class="col-12 col-xl-5">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">账号分布</h2>
              <p class="section-copy mb-0">用于快速发现高频操作账号。</p>
            </div>
          </div>
          <div class="table-responsive">
            <table class="table align-middle mb-0">
              <thead><tr><th>账号</th><th>次数</th></tr></thead>
              <tbody>{''.join(user_rows) if user_rows else '<tr><td colspan="2" class="text-secondary">暂无审计记录。</td></tr>'}</tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">最近操作</h2>
          <p class="section-copy mb-0">按时间倒序显示，保留请求编号方便和服务器日志对照。</p>
        </div>
        <div class="d-flex flex-wrap gap-2">
          <a class="btn btn-outline-dark" href="/access-stats">查看访问统计</a>
          <a class="btn btn-outline-dark" href="/request-trace">请求编号排障</a>
          <a class="btn btn-outline-dark" href="/accounts">返回账号管理</a>
        </div>
      </div>
      <div class="form-panel p-3 mb-3">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-xl-4">
            <label class="form-label">搜索</label>
            <input class="form-control" id="audit-search" placeholder="账号、动作、说明、目标、IP、请求编号">
          </div>
          <div class="col-12 col-md-4 col-xl-3">
            <label class="form-label">动作类型</label>
            <select class="form-select" id="audit-action-filter">
              <option value="">全部动作</option>
              {''.join(action_options)}
            </select>
          </div>
          <div class="col-12 col-md-4 col-xl-3">
            <label class="form-label">账号</label>
            <select class="form-select" id="audit-user-filter">
              <option value="">全部账号</option>
              {''.join(user_options)}
            </select>
          </div>
          <div class="col-12 col-md-4 col-xl-2">
            <button class="btn btn-outline-dark w-100" type="button" id="audit-filter-reset">重置</button>
          </div>
        </div>
        <div class="small text-secondary mt-2"><span id="audit-visible-count">{len(logs)}</span> / {len(logs)} 条记录</div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle mb-0">
          <thead><tr><th>时间</th><th>账号</th><th>动作</th><th>说明</th><th>目标</th><th>来源/请求</th></tr></thead>
          <tbody>
            {''.join(recent_rows) if recent_rows else '<tr><td colspan="6" class="text-secondary">暂无审计记录。</td></tr>'}
            <tr id="audit-empty-row" class="d-none"><td colspan="6" class="text-secondary">没有符合筛选条件的审计记录。</td></tr>
          </tbody>
        </table>
      </div>
    </section>
    <script>
      (function () {{
        const searchInput = document.getElementById("audit-search");
        const actionFilter = document.getElementById("audit-action-filter");
        const userFilter = document.getElementById("audit-user-filter");
        const resetButton = document.getElementById("audit-filter-reset");
        const visibleCount = document.getElementById("audit-visible-count");
        const emptyRow = document.getElementById("audit-empty-row");
        const rows = Array.from(document.querySelectorAll("[data-audit-row]"));

        function applyFilters() {{
          const keyword = (searchInput && searchInput.value || "").trim().toLowerCase();
          const action = actionFilter && actionFilter.value || "";
          const username = userFilter && userFilter.value || "";
          let shown = 0;
          rows.forEach((row) => {{
            const matchesKeyword = !keyword || (row.getAttribute("data-audit-keyword") || "").includes(keyword);
            const matchesAction = !action || row.getAttribute("data-audit-action") === action;
            const matchesUser = !username || row.getAttribute("data-audit-username") === username;
            const visible = matchesKeyword && matchesAction && matchesUser;
            row.classList.toggle("d-none", !visible);
            if (visible) shown += 1;
          }});
          if (visibleCount) visibleCount.textContent = String(shown);
          if (emptyRow) emptyRow.classList.toggle("d-none", shown !== 0 || rows.length === 0);
        }}

        [searchInput, actionFilter, userFilter].forEach((control) => {{
          if (control) control.addEventListener("input", applyFilters);
          if (control) control.addEventListener("change", applyFilters);
        }});
        if (resetButton) {{
          resetButton.addEventListener("click", function () {{
            if (searchInput) searchInput.value = "";
            if (actionFilter) actionFilter.value = "";
            if (userFilter) userFilter.value = "";
            applyFilters();
          }});
        }}
        document.querySelectorAll("[data-copy-text]").forEach((button) => {{
          button.addEventListener("click", function () {{
            const value = button.getAttribute("data-copy-text") || "";
            if (!value) return;
            if (navigator.clipboard && navigator.clipboard.writeText) {{
              navigator.clipboard.writeText(value).catch(function () {{}});
            }}
          }});
        }});
        applyFilters();
      }})();
    </script>
    """
    return layout("操作审计", body, ctx, alert=alert)


def _render_trace_audit_rows(rows: list[dict]) -> str:
    rendered_rows = []
    for item in rows:
        action_code = str(item.get("action") or "").strip()
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        metadata_text = "；".join(
            f"{key}: {value}"
            for key, value in metadata.items()
            if value not in (None, "", [])
        )
        rendered_rows.append(
            f"""
            <tr>
              <td class="text-secondary">{escape(item.get('created_at') or '')}</td>
              <td>{escape(item.get('username') or '未记录')}</td>
              <td>
                <div>{escape(_audit_action_label(action_code))}</div>
                <div class="small text-secondary"><code>{escape(action_code)}</code></div>
              </td>
              <td class="text-break">
                <div>{escape(item.get('summary') or '')}</div>
                {f'<div class="small text-secondary mt-1">{escape(metadata_text)}</div>' if metadata_text else ''}
              </td>
              <td class="text-break">
                <div>{escape(item.get('target_type') or '')}</div>
                <div class="small text-secondary"><code>{escape(item.get('target_id') or '')}</code></div>
              </td>
              <td class="text-break small text-secondary">{escape(item.get('ip_address') or '')}</td>
            </tr>
            """
        )
    return "".join(rendered_rows) if rendered_rows else '<tr><td colspan="6" class="text-secondary">没有找到关联的操作审计记录。</td></tr>'


def get_request_trace_page(ctx: RequestContext, alert: str = "") -> str:
    request_id = form_value(ctx.query, "request_id").strip()
    trace = {"request_id": request_id, "access_logs": [], "audit_logs": []}
    schema_error = ""
    if request_id:
        try:
            trace = load_request_trace(request_id)
        except Exception as exc:
            schema_error = str(exc)
    access_logs = trace.get("access_logs", [])
    audit_logs = trace.get("audit_logs", [])
    primary_access = access_logs[0] if access_logs else {}
    status_code = int(primary_access.get("status_code") or 0)
    duration_ms = int(primary_access.get("duration_ms") or 0)
    full_path = _format_access_path(primary_access) if primary_access else ""
    diagnosis = "请输入请求编号开始查询。"
    if request_id and not access_logs and not audit_logs:
        diagnosis = "没有找到匹配记录。请确认请求编号完整，或检查访问日志是否已写入当前数据库。"
    elif status_code >= 500:
        diagnosis = "这是服务端错误。请在服务器日志里搜索同一个请求编号，优先查看异常堆栈。"
    elif status_code >= 400:
        diagnosis = "这是客户端请求错误。优先检查路径、参数、登录状态或权限。"
    elif duration_ms >= 1000:
        diagnosis = "请求已成功返回，但耗时偏高。优先检查数据库查询、导入任务或页面聚合逻辑。"
    elif request_id:
        diagnosis = "没有发现明显异常。可结合用户反馈继续查看路径、账号和操作记录。"
    access_rows = _render_access_log_rows(access_logs, empty_text="没有找到关联的访问记录。", row_limit=20)
    audit_rows = _render_trace_audit_rows(audit_logs)
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">稳定性排障</div>
      <h1 class="display-6 fw-semibold mb-3">请求编号排障</h1>
      <p class="mb-0 opacity-75">输入用户看到的请求编号，集中查看访问记录、状态码、耗时、账号、IP 和关键操作审计。</p>
    </section>
    {f'<div class="alert alert-warning">请求排障所需表结构还没有在当前数据库中更新。请先执行 PostgreSQL 表结构更新脚本。错误信息：{escape(schema_error)}</div>' if schema_error else ''}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <form method="get" action="/request-trace">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-xl-8">
            <label class="form-label">请求编号</label>
            <input class="form-control" name="request_id" value="{escape(request_id)}" placeholder="例如 req_a0de2698ce8ddaf3e41379da" autocomplete="off">
          </div>
          <div class="col-12 col-xl-4">
            <button class="btn btn-dark w-100" type="submit">查询</button>
          </div>
        </div>
      </form>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-3">
        {_stat_card("请求编号", trace.get("request_id") or "未输入", "可直接复制后去服务器日志搜索")}
        {_stat_card("状态", str(status_code) if status_code else "未找到", diagnosis)}
        {_stat_card("耗时", _duration_text(duration_ms), full_path or "没有关联访问路径")}
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">访问记录</h2>
          <p class="section-copy mb-0">同一个请求编号通常只有一条访问记录；如果经过代理重试，这里可能出现多条。</p>
        </div>
        <div class="d-flex flex-wrap gap-2">
          {_copy_request_id_control(trace.get("request_id") or request_id)}
          <a class="btn btn-outline-dark" href="/access-stats">访问统计</a>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle mb-0">
          <thead><tr><th>时间</th><th>方式</th><th>状态</th><th>耗时</th><th>页面</th><th>用户</th><th>IP</th><th>请求/User Agent</th></tr></thead>
          <tbody>{access_rows}</tbody>
        </table>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">操作审计</h2>
          <p class="section-copy mb-0">如果这个请求触发了后台关键变更，会在这里显示对应动作。</p>
        </div>
        <a class="btn btn-outline-dark" href="/audit-logs">操作审计</a>
      </div>
      <div class="table-responsive">
        <table class="table align-middle mb-0">
          <thead><tr><th>时间</th><th>账号</th><th>动作</th><th>说明</th><th>目标</th><th>IP</th></tr></thead>
          <tbody>{audit_rows}</tbody>
        </table>
      </div>
    </section>
    <script>
      (function () {{
        document.querySelectorAll("[data-copy-text]").forEach((button) => {{
          button.addEventListener("click", function () {{
            const value = button.getAttribute("data-copy-text") || "";
            if (!value) return;
            if (navigator.clipboard && navigator.clipboard.writeText) {{
              navigator.clipboard.writeText(value).catch(function () {{}});
            }}
          }});
        }});
      }})();
    </script>
    """
    return layout("请求编号排障", body, ctx, alert=alert)


def get_ai_conversations_page(ctx: RequestContext, alert: str = "") -> str:
    conversations = load_ai_conversations(100)
    rows = []
    for item in conversations:
        scope_parts = [
            item.get("region_name") or "",
            item.get("competition_name") or "",
            item.get("season_name") or "",
        ]
        scope_text = " / ".join(part for part in scope_parts if part) or "未记录范围"
        rows.append(
            f"""
            <article class="form-panel p-3 p-lg-4 mb-3">
              <div class="d-flex flex-column flex-xl-row justify-content-between gap-3 mb-3">
                <div>
                  <div class="eyebrow mb-2">AI 数据问答</div>
                  <h2 class="h5 mb-2">{escape(scope_text)}</h2>
                  <div class="d-flex flex-wrap gap-2">
                    <span class="chip">模型 {escape(item.get('model') or '未记录')}</span>
                    <span class="chip">用户 {escape(item.get('username') or '访客')}</span>
                  </div>
                </div>
                <div class="small text-secondary text-xl-end">
                  <div>{escape(item.get('created_at') or '')}</div>
                  <div class="text-break">ID {escape(item.get('conversation_id') or '')}</div>
                </div>
              </div>
              <div class="border-top pt-3">
                <div class="small text-secondary mb-1">问题</div>
                <div class="text-break">{escape(item.get('question') or '')}</div>
              </div>
              <div class="border-top pt-3 mt-3">
                <div class="small text-secondary mb-1">回答</div>
                <div class="text-break" style="white-space: pre-wrap;">{escape(item.get('answer') or '')}</div>
              </div>
            </article>
            """
        )
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">AI 审计</div>
      <h1 class="display-6 fw-semibold mb-3">AI 对话记录</h1>
      <p class="mb-0 opacity-75">保存 AI 数据分析页的用户问题、模型回答、关联赛事范围和发起用户。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">最近对话</h2>
          <p class="section-copy mb-0">显示最近 100 条 AI 数据问答记录。</p>
        </div>
        <div class="d-flex flex-wrap gap-2">
          <a class="btn btn-outline-dark" href="/ai-jobs">查看 AI 使用记录</a>
          <a class="btn btn-outline-dark" href="/ai-admin">返回 AI 管理</a>
        </div>
      </div>
      {''.join(rows) if rows else '<div class="alert alert-secondary mb-0">还没有 AI 对话记录。</div>'}
    </section>
    """
    return layout("AI 对话记录", body, ctx, alert=alert)


def get_ai_jobs_page(ctx: RequestContext, alert: str = "") -> str:
    jobs = load_ai_jobs(80)
    rows = []
    for job in jobs:
        step_items = []
        for step in job.get("steps", []):
            detail = step.get("output_summary") or step.get("error_message") or step.get("input_summary") or ""
            step_items.append(
                f"""
                <div class="border-top py-2">
                  <div class="d-flex flex-column flex-lg-row justify-content-between gap-2">
                    <div>
                      <strong>{escape(str(step.get('step_order') or ''))}. {escape(step.get('step_name') or '未知步骤')}</strong>
                      <span class="ms-2">{_ai_job_status_chip(step.get('status') or '')}</span>
                    </div>
                    <div class="small text-secondary">{escape(step.get('started_at') or '')}{' -> ' + escape(step.get('finished_at') or '') if step.get('finished_at') else ''}</div>
                  </div>
                  <div class="small text-secondary mt-2 text-break">{escape(detail)}</div>
                </div>
                """
            )
        rows.append(
            f"""
            <article class="form-panel p-3 p-lg-4 mb-3">
              <div class="d-flex flex-column flex-xl-row justify-content-between gap-3">
                <div>
                  <div class="eyebrow mb-2">{escape(AI_JOB_TYPE_LABELS.get(job.get('job_type') or '', job.get('job_type') or 'AI 任务'))}</div>
                  <h2 class="h5 mb-2 text-break">{escape(job.get('scope_key') or '未记录范围')}</h2>
                  <div class="d-flex flex-wrap gap-2">
                    {_ai_job_status_chip(job.get('status') or '')}
                    <span class="chip">模型 {escape(job.get('model') or '未记录')}</span>
                    <span class="chip">发起人 {escape(job.get('created_by') or '系统')}</span>
                  </div>
                </div>
                <div class="small text-secondary text-xl-end">
                  <div>创建 {escape(job.get('created_at') or '')}</div>
                  <div>更新 {escape(job.get('updated_at') or '')}</div>
                  <div class="text-break">ID {escape(job.get('job_id') or '')}</div>
                </div>
              </div>
              {f'<div class="alert alert-danger mt-3 mb-0">{escape(job.get("error_message") or "")}</div>' if job.get("error_message") else ''}
              <div class="mt-3">
                {''.join(step_items) if step_items else '<div class="small text-secondary">暂无步骤记录。</div>'}
              </div>
            </article>
            """
        )
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">AI 审计</div>
      <h1 class="display-6 fw-semibold mb-3">AI 使用记录</h1>
      <p class="mb-0 opacity-75">查看最近的 AI 生成任务、步骤摘要、模型调用状态和错误信息。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">最近任务</h2>
          <p class="section-copy mb-0">这里展示最近 80 条任务。提示词和输出只保留摘要，完整发布内容仍在对应比赛日、赛季、战队或选手页面维护。</p>
        </div>
        <div class="d-flex flex-wrap gap-2">
          <a class="btn btn-outline-dark" href="/ai-conversations">查看对话记录</a>
          <a class="btn btn-outline-dark" href="/ai-admin">返回 AI 管理</a>
        </div>
      </div>
      {''.join(rows) if rows else '<div class="alert alert-secondary mb-0">还没有 AI 任务记录。</div>'}
    </section>
    """
    return layout("AI 使用记录", body, ctx, alert=alert)


def get_ai_admin_page(
    ctx: RequestContext,
    alert: str = "",
    form_values: dict[str, str] | None = None,
) -> str:
    ai_settings = load_ai_daily_brief_settings()
    ai_prompt_templates = load_ai_prompt_templates()
    ai_form = {
        "base_url": str((form_values or {}).get("ai_base_url") or ai_settings.get("base_url") or "").strip(),
        "api_key": "",
        "model": str((form_values or {}).get("ai_model") or ai_settings.get("model") or legacy.DEFAULT_AI_DAILY_BRIEF_MODEL).strip() or legacy.DEFAULT_AI_DAILY_BRIEF_MODEL,
    }
    ai_prompt_form = {
        "match_day_system_prompt": str((form_values or {}).get("match_day_system_prompt") or ai_prompt_templates.get("match_day_system_prompt") or "").strip(),
        "match_day_user_prompt": str((form_values or {}).get("match_day_user_prompt") or ai_prompt_templates.get("match_day_user_prompt") or "").strip(),
        "season_summary_system_prompt": str((form_values or {}).get("season_summary_system_prompt") or ai_prompt_templates.get("season_summary_system_prompt") or "").strip(),
        "season_summary_user_prompt": str((form_values or {}).get("season_summary_user_prompt") or ai_prompt_templates.get("season_summary_user_prompt") or "").strip(),
        "player_season_summary_system_prompt": str((form_values or {}).get("player_season_summary_system_prompt") or ai_prompt_templates.get("player_season_summary_system_prompt") or "").strip(),
        "player_season_summary_user_prompt": str((form_values or {}).get("player_season_summary_user_prompt") or ai_prompt_templates.get("player_season_summary_user_prompt") or "").strip(),
        "team_season_summary_system_prompt": str((form_values or {}).get("team_season_summary_system_prompt") or ai_prompt_templates.get("team_season_summary_system_prompt") or "").strip(),
        "team_season_summary_user_prompt": str((form_values or {}).get("team_season_summary_user_prompt") or ai_prompt_templates.get("team_season_summary_user_prompt") or "").strip(),
    }
    ai_configured = bool(ai_settings.get("base_url") and ai_settings.get("api_key"))
    ai_status_text = (
        f'已启用，当前地址 {escape(ai_settings["base_url"])}，模型 {escape(ai_settings["model"])}，Key {escape(mask_api_key(ai_settings["api_key"]))}'
        if ai_configured
        else "尚未配置。配置完成后，比赛日页面、赛季页、战队页和选手页都会出现对应的 AI 生成按钮。"
    )
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">AI 控制台</div>
      <h1 class="display-6 fw-semibold mb-3">AI 管理</h1>
      <p class="mb-0 opacity-75">集中管理模型接口、提示词模板和生成任务审计。比赛数据仍以本地统计和校验结果为准。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">AI 接口配置</h2>
          <p class="section-copy mb-0">这里填写兼容 OpenAI 协议的接口配置。保存后，日报、赛季总结、战队总结和选手总结会使用该配置生成。</p>
        </div>
        <span class="chip">{'已配置' if ai_configured else '未配置'}</span>
      </div>
      <div class="form-panel p-3 p-lg-4">
        <div class="small text-secondary mb-4">{ai_status_text}</div>
        <form method="post" action="/ai-admin">
          <input type="hidden" name="action" value="save_ai_daily_brief_settings">
          <div class="row g-3">
            <div class="col-12 col-xl-5">
              <label class="form-label">Base URL</label>
              <input class="form-control" name="ai_base_url" value="{escape(ai_form['base_url'])}" placeholder="例如 https://api.openai.com/v1">
              <div class="small text-secondary mt-2">支持直接填写接口根地址，也支持直接填写到 `/chat/completions`。</div>
            </div>
            <div class="col-12 col-xl-4">
              <label class="form-label">模型名称</label>
              <input class="form-control" name="ai_model" value="{escape(ai_form['model'])}" placeholder="{escape(legacy.DEFAULT_AI_DAILY_BRIEF_MODEL)}">
              <div class="small text-secondary mt-2">多数兼容接口都需要明确指定模型，默认值可直接用于 OpenAI 官方接口。</div>
            </div>
            <div class="col-12 col-xl-3">
              <label class="form-label">API Key</label>
              <input class="form-control" name="ai_api_key" type="password" autocomplete="off" placeholder="{escape('留空则保持当前 Key' if ai_settings.get('api_key') else '输入新的 API Key')}">
              <div class="small text-secondary mt-2">为安全起见，这里不会回显已保存的 Key。</div>
            </div>
          </div>
          <div class="d-flex flex-wrap gap-2 mt-4">
            <button type="submit" class="btn btn-dark">保存 AI 配置</button>
            <a class="btn btn-outline-dark" href="/ai-jobs">查看 AI 使用记录</a>
            <a class="btn btn-outline-dark" href="/ai-conversations">查看 AI 对话记录</a>
            <a class="btn btn-outline-dark" href="/access-stats">查看访问统计</a>
            <a class="btn btn-outline-dark" href="/audit-logs">查看操作审计</a>
          </div>
        </form>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">提示词模板</h2>
          <p class="section-copy mb-0">分别配置比赛日报、赛季总结、战队赛季总结和选手赛季总结的系统提示词、用户提示词模板。用户模板支持占位符。</p>
        </div>
      </div>
      <div class="form-panel p-3 p-lg-4">
        <form method="post" action="/ai-admin">
          <input type="hidden" name="action" value="save_ai_prompt_templates">
          <div class="row g-4">
            <div class="col-12">
              <h3 class="h5 mb-3">比赛日报</h3>
            </div>
            <div class="col-12 col-xl-4">
              <label class="form-label">系统提示词</label>
              <textarea class="form-control" name="match_day_system_prompt" rows="8">{escape(ai_prompt_form['match_day_system_prompt'])}</textarea>
            </div>
            <div class="col-12 col-xl-8">
              <label class="form-label">用户提示词模板</label>
              <textarea class="form-control" name="match_day_user_prompt" rows="12">{escape(ai_prompt_form['match_day_user_prompt'])}</textarea>
              <div class="small text-secondary mt-2">可用占位符：`{"{played_on}"}`、`{"{series_count}"}`、`{"{match_count}"}`、`{"{team_board}"}`、`{"{player_board}"}`、`{"{match_details}"}`。</div>
            </div>
            <div class="col-12">
              <h3 class="h5 mb-3">赛季总结</h3>
            </div>
            <div class="col-12 col-xl-4">
              <label class="form-label">系统提示词</label>
              <textarea class="form-control" name="season_summary_system_prompt" rows="8">{escape(ai_prompt_form['season_summary_system_prompt'])}</textarea>
            </div>
            <div class="col-12 col-xl-8">
              <label class="form-label">用户提示词模板</label>
              <textarea class="form-control" name="season_summary_user_prompt" rows="14">{escape(ai_prompt_form['season_summary_user_prompt'])}</textarea>
              <div class="small text-secondary mt-2">可用占位符：`{"{competition_name}"}`、`{"{season_name}"}`、`{"{match_count}"}`、`{"{team_count}"}`、`{"{player_count}"}`、`{"{team_board}"}`、`{"{player_board}"}`、`{"{mvp_board}"}`、`{"{stage_summary}"}`、`{"{match_day_distribution}"}`。</div>
            </div>
            <div class="col-12">
              <h3 class="h5 mb-3">选手赛季总结</h3>
            </div>
            <div class="col-12 col-xl-4">
              <label class="form-label">系统提示词</label>
              <textarea class="form-control" name="player_season_summary_system_prompt" rows="8">{escape(ai_prompt_form['player_season_summary_system_prompt'])}</textarea>
            </div>
            <div class="col-12 col-xl-8">
              <label class="form-label">用户提示词模板</label>
              <textarea class="form-control" name="player_season_summary_user_prompt" rows="16">{escape(ai_prompt_form['player_season_summary_user_prompt'])}</textarea>
              <div class="small text-secondary mt-2">可用占位符：`{"{player_name}"}`、`{"{team_name}"}`、`{"{competition_name}"}`、`{"{season_name}"}`、`{"{rank}"}`、`{"{games_played}"}`、`{"{record}"}`、`{"{overall_win_rate}"}`、`{"{villagers_win_rate}"}`、`{"{werewolves_win_rate}"}`、`{"{points_total}"}`、`{"{average_points}"}`、`{"{stance_summary}"}`、`{"{role_summary}"}`、`{"{season_player_board}"}`、`{"{season_team_board}"}`、`{"{recent_matches}"}`。</div>
            </div>
            <div class="col-12">
              <h3 class="h5 mb-3">战队赛季总结</h3>
            </div>
            <div class="col-12 col-xl-4">
              <label class="form-label">系统提示词</label>
              <textarea class="form-control" name="team_season_summary_system_prompt" rows="8">{escape(ai_prompt_form['team_season_summary_system_prompt'])}</textarea>
            </div>
            <div class="col-12 col-xl-8">
              <label class="form-label">用户提示词模板</label>
              <textarea class="form-control" name="team_season_summary_user_prompt" rows="16">{escape(ai_prompt_form['team_season_summary_user_prompt'])}</textarea>
              <div class="small text-secondary mt-2">可用占位符：`{"{team_name}"}`、`{"{competition_name}"}`、`{"{season_name}"}`、`{"{rank}"}`、`{"{player_count}"}`、`{"{matches_represented}"}`、`{"{points_total}"}`、`{"{points_per_match}"}`、`{"{win_rate}"}`、`{"{stance_rate}"}`、`{"{season_team_board}"}`、`{"{roster_board}"}`、`{"{recent_matches}"}`。</div>
            </div>
          </div>
          <div class="d-flex flex-wrap gap-2 mt-4">
            <button type="submit" class="btn btn-dark">保存提示词模板</button>
          </div>
        </form>
      </div>
    </section>
    """
    return layout("AI 管理", body, ctx, alert=alert)


def handle_ai_admin(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_ai_admin_page(ctx))

    action = form_value(ctx.form, "action")
    if action == "save_ai_daily_brief_settings":
        base_url = form_value(ctx.form, "ai_base_url").strip()
        model = form_value(ctx.form, "ai_model", legacy.DEFAULT_AI_DAILY_BRIEF_MODEL).strip()
        api_key = form_value(ctx.form, "ai_api_key").strip()
        existing_settings = load_ai_daily_brief_settings()
        if not base_url:
            return start_response_html(
                start_response,
                "200 OK",
                get_ai_admin_page(
                    ctx,
                    alert="请先填写 AI 接口 Base URL。",
                    form_values={
                        "ai_base_url": base_url,
                        "ai_model": model,
                    },
                ),
            )
        if not api_key and not existing_settings.get("api_key"):
            return start_response_html(
                start_response,
                "200 OK",
                get_ai_admin_page(
                    ctx,
                    alert="请先填写 AI 接口 API Key。",
                    form_values={
                        "ai_base_url": base_url,
                        "ai_model": model,
                    },
                ),
            )
        save_ai_daily_brief_settings(
            base_url=base_url,
            api_key=api_key,
            model=model,
            preserve_existing_api_key=True,
        )
        return start_response_html(
            start_response,
            "200 OK",
            get_ai_admin_page(ctx, alert="AI 配置已保存。"),
        )

    if action == "save_ai_prompt_templates":
        match_day_system_prompt = form_value(ctx.form, "match_day_system_prompt").strip()
        match_day_user_prompt = form_value(ctx.form, "match_day_user_prompt").strip()
        season_summary_system_prompt = form_value(ctx.form, "season_summary_system_prompt").strip()
        season_summary_user_prompt = form_value(ctx.form, "season_summary_user_prompt").strip()
        player_season_summary_system_prompt = form_value(ctx.form, "player_season_summary_system_prompt").strip()
        player_season_summary_user_prompt = form_value(ctx.form, "player_season_summary_user_prompt").strip()
        team_season_summary_system_prompt = form_value(ctx.form, "team_season_summary_system_prompt").strip()
        team_season_summary_user_prompt = form_value(ctx.form, "team_season_summary_user_prompt").strip()
        if not all(
            [
                match_day_system_prompt,
                match_day_user_prompt,
                season_summary_system_prompt,
                season_summary_user_prompt,
                player_season_summary_system_prompt,
                player_season_summary_user_prompt,
                team_season_summary_system_prompt,
                team_season_summary_user_prompt,
            ]
        ):
            return start_response_html(
                start_response,
                "200 OK",
                get_ai_admin_page(
                    ctx,
                    alert="八个提示词模板都需要填写。",
                    form_values={
                        "match_day_system_prompt": match_day_system_prompt,
                        "match_day_user_prompt": match_day_user_prompt,
                        "season_summary_system_prompt": season_summary_system_prompt,
                        "season_summary_user_prompt": season_summary_user_prompt,
                        "player_season_summary_system_prompt": player_season_summary_system_prompt,
                        "player_season_summary_user_prompt": player_season_summary_user_prompt,
                        "team_season_summary_system_prompt": team_season_summary_system_prompt,
                        "team_season_summary_user_prompt": team_season_summary_user_prompt,
                    },
                ),
            )
        save_ai_prompt_templates(
            match_day_system_prompt=match_day_system_prompt,
            match_day_user_prompt=match_day_user_prompt,
            season_summary_system_prompt=season_summary_system_prompt,
            season_summary_user_prompt=season_summary_user_prompt,
            player_season_summary_system_prompt=player_season_summary_system_prompt,
            player_season_summary_user_prompt=player_season_summary_user_prompt,
            team_season_summary_system_prompt=team_season_summary_system_prompt,
            team_season_summary_user_prompt=team_season_summary_user_prompt,
        )
        return start_response_html(
            start_response,
            "200 OK",
            get_ai_admin_page(ctx, alert="AI 提示词模板已保存。"),
        )

    return start_response_html(
        start_response,
        "200 OK",
        get_ai_admin_page(ctx, alert="未识别的操作。"),
    )
