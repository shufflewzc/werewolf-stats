from __future__ import annotations

from html import escape

import web_app as legacy

RequestContext = legacy.RequestContext
form_value = legacy.form_value
layout = legacy.layout
load_access_overview = legacy.load_access_overview
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


def get_access_stats_page(ctx: RequestContext, alert: str = "") -> str:
    overview = load_access_overview(100)
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
    recent_rows = []
    for row in overview.get("recent_logs", []):
        query_string = str(row.get("query_string") or "").strip()
        full_path = str(row.get("path") or "/")
        if query_string:
            full_path += "?" + query_string
        recent_rows.append(
            f"""
            <tr>
              <td class="text-secondary">{escape(row.get('created_at') or '')}</td>
              <td>{escape(row.get('method') or '')}</td>
              <td class="text-break"><code>{escape(full_path)}</code></td>
              <td>{escape(row.get('username') or '访客')}</td>
              <td class="text-break">{escape(row.get('ip_address') or '')}</td>
              <td class="text-break small text-secondary">{escape(row.get('user_agent') or '')}</td>
            </tr>
            """
        )
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">运营统计</div>
      <h1 class="display-6 fw-semibold mb-3">访问统计</h1>
      <p class="mb-0 opacity-75">记录站内页面访问、登录用户、来源 IP 和浏览器信息，静态资源不计入。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-3">
        {_stat_card("累计访问", str(overview.get("total_visits") or 0), "数据库中保存的全部访问记录")}
        {_stat_card("今日访问", str(overview.get("today_visits") or 0), "按北京时间自然日统计")}
        {_stat_card("独立 IP", str(overview.get("unique_ip_count") or 0), "累计出现过的访问 IP 数")}
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
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
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">最近访问</h2>
          <p class="section-copy mb-0">显示最近 100 条访问记录。</p>
        </div>
        <a class="btn btn-outline-dark" href="/accounts">返回账号管理</a>
      </div>
      <div class="table-responsive">
        <table class="table align-middle mb-0">
          <thead><tr><th>时间</th><th>方式</th><th>页面</th><th>用户</th><th>IP</th><th>User Agent</th></tr></thead>
          <tbody>{''.join(recent_rows) if recent_rows else '<tr><td colspan="6" class="text-secondary">暂无访问记录。</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    """
    return layout("访问统计", body, ctx, alert=alert)


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
