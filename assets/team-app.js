(function () {
  const bootstrap = window.__WEREWOLF_TEAM_BOOTSTRAP__ || {};
  const root = document.getElementById("team-app");

  if (!root) return;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function clampWidth(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number)) return 0;
    return Math.max(0, Math.min(100, number));
  }

  function renderAlert(message) {
    if (!message) return "";
    return `<div class="competitions-alert">${escapeHtml(message)}</div>`;
  }

  function renderMetrics(metrics) {
    const items = Array.isArray(metrics) ? metrics : [];
    if (!items.length) return "";
    return `
      <section class="competitions-metrics-grid team-detail-metrics-grid">
        ${items.map((item) => `
          <article class="competitions-metric team-detail-metric">
            <div class="competitions-stat-label">${escapeHtml(item.label)}</div>
            <div class="competitions-stat-value">${escapeHtml(item.value)}</div>
            <p class="competitions-card-copy">${escapeHtml(item.copy || "")}</p>
          </article>
        `).join("")}
      </section>
    `;
  }

  function renderInsights(team, insights) {
    const stageGroups = Array.isArray(team.stage_groups) ? team.stage_groups : [];
    return `
      <aside class="competitions-panel team-detail-insight-card">
        <div>
          <div class="competitions-section-kicker">Season Insight</div>
          <h2 class="competitions-section-title">赛季观察</h2>
          <p class="competitions-copy">把战绩、积分效率、门派和赛段分组收在一起，快速判断这支战队当前状态。</p>
        </div>
        <div class="team-detail-meter-row">
          <div class="team-detail-meter-head"><strong>胜率表现</strong><span>${escapeHtml(insights.win_rate || "0%")}</span></div>
          <div class="team-detail-meter-track"><div class="team-detail-meter-fill" style="width:${clampWidth(insights.win_width)}%"></div></div>
        </div>
        <div class="team-detail-meter-row">
          <div class="team-detail-meter-head"><strong>积分效率</strong><span>场均 ${escapeHtml(insights.points_per_match || "0.0")}</span></div>
          <div class="team-detail-meter-track"><div class="team-detail-meter-fill" style="width:${clampWidth(insights.points_width)}%"></div></div>
        </div>
        <div class="team-detail-note-grid">
          <div class="team-detail-note-item"><span>Captain</span><strong>${escapeHtml(team.captain || "暂未认领")}</strong></div>
          <div class="team-detail-note-item"><span>Guild</span><strong>${escapeHtml(team.guild || "未加入门派")}</strong></div>
          <div class="team-detail-note-item"><span>Stage Group</span><strong>${escapeHtml(insights.stage_summary || "暂未设置")}</strong></div>
          <div class="team-detail-note-item"><span>Notes</span><strong>${escapeHtml(team.notes || "暂无战队备注")}</strong></div>
        </div>
        ${stageGroups.length ? `
          <div class="team-detail-stage-row">
            ${stageGroups.map((item) => `<span>${escapeHtml(item.label)} · ${escapeHtml(item.group)}</span>`).join("")}
          </div>
        ` : ""}
      </aside>
    `;
  }

  function renderRoster(roster) {
    const items = Array.isArray(roster) ? roster : [];
    if (!items.length) {
      return `<div class="competitions-empty-state">当前口径下暂无阵容成员。</div>`;
    }
    return `
      <div class="team-detail-roster-grid">
        ${items.map((player) => `
          <a class="team-detail-player-card" href="${escapeHtml(player.href || "#")}">
            <img class="team-detail-player-photo" src="${escapeHtml(player.photo || "/assets/players/default-player.svg")}" alt="${escapeHtml(player.name || "选手")}" loading="lazy">
            <div class="team-detail-player-main">
              <div class="team-detail-player-name">${escapeHtml(player.name || "未命名选手")}</div>
              <p>${escapeHtml(player.notes || "暂无选手备注")}</p>
              <div class="team-detail-player-tags">
                <span>${escapeHtml(player.matches)} 局</span>
                <span>${escapeHtml(player.win_rate)}</span>
                <span>${escapeHtml(player.points)} 分</span>
                <span>${escapeHtml(player.top_role || "-")}</span>
              </div>
            </div>
          </a>
        `).join("")}
      </div>
    `;
  }

  function renderMatches(matches) {
    const items = Array.isArray(matches) ? matches : [];
    if (!items.length) {
      return `<div class="competitions-empty-state">当前口径下暂无最近比赛。</div>`;
    }
    return `
      <div class="team-detail-match-grid">
        ${items.map((match) => `
          <a class="team-detail-match-card" href="${escapeHtml(match.href || "#")}">
            <div class="team-detail-match-top">
              <span>${escapeHtml(match.played_on || "未定日期")}</span>
              <strong>${escapeHtml(match.result || "-")}</strong>
            </div>
            <div class="team-detail-match-title">${escapeHtml(match.stage_label || "赛段")} · 第 ${escapeHtml(match.round || 0)} 轮 第 ${escapeHtml(match.game_no || 0)} 局</div>
            <div class="team-detail-match-meta">
              <span>${escapeHtml(match.format || "未记录板型")}</span>
              <span>${escapeHtml(match.points)} 分</span>
            </div>
          </a>
        `).join("")}
      </div>
    `;
  }

  function renderTeam(payload) {
    const team = payload.team || {};
    const actions = payload.actions || {};
    const insights = payload.insights || {};
    if (payload.title) document.title = payload.title;
    root.innerHTML = `
      ${renderAlert(payload.alert || bootstrap.alert)}
      <section class="team-detail-hero">
        <div class="team-detail-hero-left">
          <article class="competitions-panel team-detail-hero-main">
            <div class="team-detail-logo-wrap">
              <img class="team-detail-logo" src="${escapeHtml(team.logo || "/assets/teams/default.svg")}" alt="${escapeHtml(team.name || "战队")} 队标">
            </div>
            <div class="team-detail-hero-copy">
              <div class="competitions-section-kicker">Team Dossier</div>
              <h1 class="competitions-title">${escapeHtml(team.name || "战队详情")}</h1>
              <p class="competitions-copy">${escapeHtml(team.notes || "暂无战队备注")}</p>
              <div class="team-detail-meta-row">
                <span>${escapeHtml(team.short_name || "未设置简称")}</span>
                <span>${escapeHtml(team.competition || "全部赛事")}</span>
                <span>${escapeHtml(team.season || "全部赛季")}</span>
                <span>${escapeHtml(team.status_label || "状态未知")}</span>
              </div>
              <div class="competitions-hero-actions team-detail-actions">
                <a class="competitions-button competitions-button-secondary" href="${escapeHtml(actions.teams_href || "/teams")}">返回战队列表</a>
                <a class="competitions-button competitions-button-secondary" href="${escapeHtml(actions.competition_href || "/competitions")}">查看比赛中心</a>
                ${actions.manage_href ? `<a class="competitions-button competitions-button-primary" href="${escapeHtml(actions.manage_href)}">管理战队</a>` : ""}
                <a class="competitions-button competitions-button-secondary" href="${escapeHtml(actions.legacy_href || bootstrap.legacyHref || "#")}">查看旧版</a>
              </div>
            </div>
          </article>
          ${renderMetrics(payload.metrics)}
        </div>
        ${renderInsights(team, insights)}
      </section>
      <section class="competitions-panel team-detail-section">
        <div class="competitions-section-head">
          <div>
            <div class="competitions-section-kicker">Roster</div>
            <h2 class="competitions-section-title">赛季阵容</h2>
            <p class="competitions-copy">展示当前赛季成员，以及每位选手在这支战队下的局数、胜率和积分。</p>
          </div>
        </div>
        ${renderRoster(payload.roster)}
      </section>
      <section class="competitions-panel team-detail-section">
        <div class="competitions-section-head">
          <div>
            <div class="competitions-section-kicker">Recent Matches</div>
            <h2 class="competitions-section-title">最近比赛</h2>
            <p class="competitions-copy">按日期、轮次和局数展示最近比赛，点击可以进入比赛详情。</p>
          </div>
        </div>
        ${renderMatches(payload.matches)}
      </section>
    `;
  }

  function renderError(message, legacyHref) {
    root.innerHTML = `
      <section class="competitions-panel competitions-empty-state">
        <div class="competitions-section-kicker">Load Failed</div>
        <h1 class="competitions-title">战队详情加载失败</h1>
        <p class="competitions-copy">${escapeHtml(message || "unknown error")}</p>
        <a class="competitions-button competitions-button-secondary" href="${escapeHtml(legacyHref || bootstrap.legacyHref || "/teams")}">打开旧版团队页</a>
      </section>
    `;
  }

  async function loadTeamPage() {
    const endpoint = `${bootstrap.apiEndpoint || ""}${window.location.search || ""}`;
    try {
      const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
      const payload = await response.json();
      if (!response.ok || payload.error) {
        throw Object.assign(new Error(payload.error || `HTTP ${response.status}`), { payload });
      }
      renderTeam(payload);
    } catch (error) {
      renderError(error instanceof Error ? error.message : "unknown error", error && error.payload && error.payload.legacy_href);
    }
  }

  loadTeamPage();
})();
