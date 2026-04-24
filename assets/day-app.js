(function () {
  const bootstrap = window.__WEREWOLF_MATCH_DAY_BOOTSTRAP__ || {};
  const root = document.getElementById("match-day-app");

  if (!root) {
    return;
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function renderAlert(message) {
    if (!message) {
      return "";
    }
    return `<div class="competitions-alert">${escapeHtml(message)}</div>`;
  }

  function renderMetrics(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return "";
    }
    return `
      <section class="competitions-metrics-grid match-day-metrics-grid">
        ${items
          .map(
            (item) => `
              <article class="competitions-metric match-day-metric-card">
                <div class="competitions-stat-label">${escapeHtml(item.label)}</div>
                <strong>${escapeHtml(item.value)}</strong>
                <div class="competitions-meta-text">${escapeHtml(item.copy)}</div>
              </article>
            `
          )
          .join("")}
      </section>
    `;
  }

  function renderAiReport(payload) {
    const report = payload.ai_report || {};
    const actions = [];
    if (report.can_generate) {
      actions.push(`
        <form method="post" action="${escapeHtml(report.action_path || "")}" class="competitions-inline-form">
          <input type="hidden" name="action" value="generate_ai_daily_brief">
          <button type="submit" class="competitions-button competitions-button-primary">${escapeHtml(
            report.generate_label || "生成 AI 日报"
          )}</button>
        </form>
      `);
    } else if (report.configure_href) {
      actions.push(
        `<a class="competitions-button competitions-button-secondary" href="${escapeHtml(
          report.configure_href
        )}">前往账号管理配置 AI 接口</a>`
      );
    }

    const editor = report.can_edit
      ? `
        <div class="competitions-form-panel" style="margin-top: 18px;">
          <h3 class="competitions-section-title">管理员编辑日报</h3>
          <p class="competitions-copy">可以直接修改当前日报正文。保存后会立即覆盖展示内容。</p>
          <form method="post" action="${escapeHtml(report.action_path || "")}">
            <input type="hidden" name="action" value="save_ai_daily_brief">
            <div class="competitions-form-field">
              <textarea class="competitions-textarea" name="report_content" rows="12">${escapeHtml(
                report.content || ""
              )}</textarea>
            </div>
            <div class="competitions-hero-actions">
              <button type="submit" class="competitions-button competitions-button-secondary">保存人工编辑</button>
            </div>
          </form>
        </div>
      `
      : "";

    return report.exists
      ? `
        <section class="competitions-panel competitions-section">
          <div class="competitions-section-head">
            <div>
              <div class="competitions-section-kicker">AI Daily Brief</div>
              <h2 class="competitions-section-title">AI 比赛日报</h2>
              <p class="competitions-copy">基于当天已录入比赛数据生成的简版赛事日报，可随比赛补录进度反复重生成。</p>
            </div>
            <div class="competitions-hero-actions">${actions.join("")}</div>
          </div>
          <div class="competitions-meta-text">生成时间 ${escapeHtml(report.generated_at)} · 模型 ${escapeHtml(
          report.model
        )}</div>
          <div class="competitions-editorial" style="margin-top: 16px;">${report.html || ""}</div>
          ${editor}
        </section>
      `
      : `
        <section class="competitions-panel competitions-section">
          <div class="competitions-section-head">
            <div>
              <div class="competitions-section-kicker">AI Daily Brief</div>
              <h2 class="competitions-section-title">AI 比赛日报</h2>
              <p class="competitions-copy">${escapeHtml(report.empty_copy || "当前还没有生成日报。")}</p>
            </div>
            <div class="competitions-hero-actions">${actions.join("")}</div>
          </div>
        </section>
      `;
  }

  function renderTeamLeaderboard(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return "";
    }
    return `
      <section class="competitions-panel competitions-section match-day-leaderboard-section">
        <div class="competitions-section-head">
          <div>
            <div class="competitions-section-kicker">Day Leaderboard</div>
            <h2 class="competitions-section-title">战队积分日榜</h2>
            <p class="competitions-copy">只统计当天已完成补录的比赛，默认按总积分从高到低排序。</p>
          </div>
        </div>
        <div class="competitions-table-panel match-day-leaderboard-panel">
          <table class="competitions-table match-day-leaderboard-table">
            <thead>
              <tr><th>排名</th><th>战队</th><th>场次</th><th>胜率</th><th>总积分</th></tr>
            </thead>
            <tbody>
              ${items
                .map(
                  (item) => `
                    <tr>
                      <td>${escapeHtml(item.rank)}</td>
                      <td><a href="${escapeHtml(item.href)}">${escapeHtml(item.name)}</a></td>
                      <td>${escapeHtml(item.matches_represented)}</td>
                      <td>${escapeHtml(item.win_rate)}</td>
                      <td>${escapeHtml(item.points_total)}</td>
                    </tr>
                  `
                )
                .join("")}
            </tbody>
          </table>
        </div>
      </section>
    `;
  }

  function renderParticipantChips(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return '<div class="match-day-empty-line">暂无队员明细</div>';
    }
    return `
      <div class="match-day-participants">
        ${items
          .map(
            (player) => `
              <a class="match-day-player-chip" href="${escapeHtml(player.player_href)}">
                <span class="match-day-seat">${escapeHtml(player.seat)}</span>
                <span class="match-day-player-main">
                  <strong>${escapeHtml(player.player_name)}</strong>
                  <small>${escapeHtml(player.team_name)} · ${escapeHtml(player.role)}</small>
                </span>
                <span class="match-day-points">${escapeHtml(player.points)}</span>
              </a>
            `
          )
          .join("")}
      </div>
    `;
  }

  function renderCompetitionSections(items) {
    return (items || [])
      .map(
        (section) => `
          <section class="competitions-panel competitions-section match-day-section">
            <div class="competitions-section-head match-day-section-head">
              <div>
                <div class="competitions-section-kicker">${escapeHtml(section.series_name)} · ${escapeHtml(
          section.region_name
        )}</div>
                <h2 class="competitions-section-title">${escapeHtml(section.competition_name)}</h2>
                <p class="competitions-section-copy">${escapeHtml(section.copy)}</p>
              </div>
              <div class="competitions-card-actions">
                <a class="competitions-button competitions-button-secondary" href="${escapeHtml(
                  section.competition_href
                )}">进入该赛事页</a>
              </div>
            </div>
            <div class="match-day-match-grid">
              ${(section.matches || [])
                .map(
                  (match) => `
                    <article class="match-day-match-card">
                      <div class="match-day-match-head">
                        <div>
                          <div class="competitions-card-kicker">${escapeHtml(match.match_id)}</div>
                          <h3 class="competitions-card-title">${escapeHtml(match.stage_label)} · 第 ${escapeHtml(
                    match.round
                  )} 轮 第 ${escapeHtml(match.game_no)} 局</h3>
                        </div>
                        <a class="competitions-button competitions-button-secondary" href="${escapeHtml(
                          match.detail_href
                        )}">详情</a>
                      </div>
                      <div class="match-day-match-meta">${escapeHtml(match.meta_text)}</div>
                      ${renderParticipantChips(match.participants || [])}
                    </article>
                  `
                )
                .join("")}
            </div>
          </section>
        `
      )
      .join("");
  }

  function renderMatchDay(payload) {
    const hero = payload.hero || {};
    const side = payload.hero_side || {};
    root.innerHTML = `
      <div class="competitions-layout match-day-layout">
        ${renderAlert(payload.alert || bootstrap.alert)}
        <section class="competitions-hero match-day-hero">
          <article class="competitions-panel competitions-hero-main">
            <div class="competitions-section-kicker">Match Day Frontend</div>
            <h1 class="competitions-title">${escapeHtml(hero.title || "比赛日")}</h1>
            <p class="competitions-copy">${escapeHtml(hero.copy || "")}</p>
            <div class="competitions-hero-actions">
              <a class="competitions-button competitions-button-secondary" href="${escapeHtml(
                payload.back_href || "/dashboard"
              )}">返回上一页</a>
              <a class="competitions-button competitions-button-secondary" href="${escapeHtml(
                payload.legacy_href || "#"
              )}">查看旧版比赛日页</a>
            </div>
          </article>
          <aside class="competitions-panel competitions-hero-side">
            <div class="competitions-panel-kicker">Daily Overview</div>
            <h2 class="competitions-section-title">${escapeHtml(side.played_on || "")}</h2>
            <div class="competitions-sidebar-grid">
              <div class="competitions-side-metric"><div class="competitions-stat-label">系列赛</div><strong>${escapeHtml(
                side.series_count || "0"
              )}</strong><div class="competitions-meta-text">当天开赛系列赛</div></div>
              <div class="competitions-side-metric"><div class="competitions-stat-label">场次</div><strong>${escapeHtml(
                side.match_count || "0"
              )}</strong><div class="competitions-meta-text">当天完整对局</div></div>
              <div class="competitions-side-metric"><div class="competitions-stat-label">战队</div><strong>${escapeHtml(
                side.team_count || "0"
              )}</strong><div class="competitions-meta-text">已补录比赛战队</div></div>
              <div class="competitions-side-metric"><div class="competitions-stat-label">队员</div><strong>${escapeHtml(
                side.player_count || "0"
              )}</strong><div class="competitions-meta-text">已补录比赛人数</div></div>
            </div>
          </aside>
        </section>
        ${renderMetrics(payload.metrics || [])}
        ${renderAiReport(payload)}
        ${renderTeamLeaderboard(payload.team_leaderboard || [])}
        ${renderCompetitionSections(payload.competitions || [])}
      </div>
    `;
  }

  function renderError(message) {
    root.innerHTML = `
      <section class="competitions-error-shell">
        <div class="competitions-loading-kicker">Load Failed</div>
        <h1>比赛日页面加载失败</h1>
        <p>${escapeHtml(message)}</p>
      </section>
    `;
  }

  async function loadMatchDay() {
    const endpoint = `${bootstrap.apiEndpoint || ""}${window.location.search || ""}`;
    try {
      const response = await fetch(endpoint, {
        headers: {
          Accept: "application/json",
        },
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      renderMatchDay(payload);
    } catch (error) {
      renderError(error instanceof Error ? error.message : "unknown error");
    }
  }

  loadMatchDay();
})();
