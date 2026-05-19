from __future__ import annotations

from html import escape

import web_app as legacy

RequestContext = legacy.RequestContext
form_value = legacy.form_value
layout = legacy.layout
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
      <h1 class="display-6 fw-semibold mb-3">AI 任务历史</h1>
      <p class="mb-0 opacity-75">查看最近的 AI 生成任务、步骤摘要、模型调用状态和错误信息。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">最近任务</h2>
          <p class="section-copy mb-0">这里展示最近 80 条任务。提示词和输出只保留摘要，完整发布内容仍在对应比赛日、赛季、战队或选手页面维护。</p>
        </div>
        <a class="btn btn-outline-dark" href="/ai-admin">返回 AI 管理</a>
      </div>
      {''.join(rows) if rows else '<div class="alert alert-secondary mb-0">还没有 AI 任务记录。</div>'}
    </section>
    """
    return layout("AI 任务历史", body, ctx, alert=alert)


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
            <a class="btn btn-outline-dark" href="/ai-jobs">查看 AI 任务历史</a>
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
