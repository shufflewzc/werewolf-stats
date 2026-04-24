(function () {
  const bootstrap = window.__WEREWOLF_TEAMS_BOOTSTRAP__ || {};
  const root = document.getElementById("teams-app");
  if (!root) return;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function renderAlert(message) {
    return message ? `<div class="competitions-alert">${escapeHtml(message)}</div>` : "";
  }

  function renderChipLinks(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return '<div class="competitions-chip-empty">当前没有可切换的选项。</div>';
    }
    return `
      <div class="competitions-chip-list">
        ${items.map((item) => `
          <a class="competitions-chip${item.active ? " is-active" : ""}" href="${escapeHtml(item.href)}">${escapeHtml(item.label)}</a>
        `).join("")}
      </div>
    `;
  }

  function renderSeasonSelect(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return '<div class="competitions-chip-empty">先选择赛事后再切换赛季。</div>';
    }
    return `
      <select class="competitions-select" data-season-switcher>
        ${items.map((item) => `<option value="${escapeHtml(item.href)}"${item.selected ? " selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}
      </select>
    `;
  }

  function renderMetrics(items) {
    if (!Array.isArray(items)) return "";
    return `
      <section class="competitions-metrics-grid teams-metrics-grid">
        ${items.map((item) => `
          <article class="competitions-metric teams-metric-card">
            <div class="competitions-stat-label">${escapeHtml(item.label)}</div>
            <div class="competitions-metric-value">${escapeHtml(item.value)}</div>
            <div class="competitions-meta-text">${escapeHtml(item.copy)}</div>
          </article>
        `).join("")}
      </section>
    `;
  }

  function renderTeams(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return `
        <div class="competitions-empty-state">
          <div class="competitions-card-kicker">Teams Empty</div>
          <h3>当前范围还没有战队</h3>
          <p>可以先进入后台维护战队，或切换到其他赛区/赛事查看。</p>
        </div>
      `;
    }
    return `
      <div class="teams-grid">
        ${items.map((team) => `
          <a class="competitions-card teams-card" href="${escapeHtml(team.href)}">
            <div class="teams-card-head">
              <span class="teams-rank">#${escapeHtml(team.rank)}</span>
              <img class="teams-logo" src="${escapeHtml(team.logo)}" alt="${escapeHtml(team.name)}">
              <div class="teams-title-block">
                <h3 class="competitions-card-title teams-title">${escapeHtml(team.name)}</h3>
                <div class="competitions-meta-text">${escapeHtml(team.competition_name || "未绑定赛事")} · ${escapeHtml(team.season_name || "未设置赛季")}</div>
              </div>
            </div>
            <div class="teams-score-row">
              <div><span>积分</span><strong>${escapeHtml(team.points_total)}</strong></div>
              <div><span>胜率</span><strong>${escapeHtml(team.win_rate)}</strong></div>
              <div><span>出赛</span><strong>${escapeHtml(team.matches_represented)} 场</strong></div>
            </div>
            <div class="teams-meta-row">
              <span>${escapeHtml(team.player_count)} 名队员</span>
              <span>${escapeHtml(team.wins)} 胜 / ${escapeHtml(team.losses)} 负</span>
              <span>均分 ${escapeHtml(team.average_points)}</span>
            </div>
          </a>
        `).join("")}
      </div>
    `;
  }

  function renderDashboard(payload) {
    const scope = payload.scope || {};
    const filters = scope.filters || {};
    root.innerHTML = `
      <div class="competitions-layout teams-layout">
        ${renderAlert(bootstrap.alert)}
        <section class="competitions-panel competitions-hero-main teams-hero">
          <div class="competitions-section-kicker">Teams Center</div>
          <h1 class="competitions-title">战队中心</h1>
          <p class="competitions-copy">${escapeHtml(scope.description || "查看当前赛区和赛事范围下的战队积分、胜率和出赛情况。")}</p>
          <div class="competitions-filter-grid teams-filter-grid">
            <section class="competitions-filter-card"><div class="competitions-filter-label">赛区切换</div>${renderChipLinks(filters.regions)}</section>
            <section class="competitions-filter-card"><div class="competitions-filter-label">系列赛切换</div>${renderChipLinks(filters.series)}</section>
            <section class="competitions-filter-card"><div class="competitions-filter-label">赛事切换</div>${renderChipLinks(filters.competitions)}</section>
            <section class="competitions-filter-card"><div class="competitions-filter-label">赛季切换</div>${renderSeasonSelect(filters.seasons)}</section>
          </div>
          <div class="competitions-card-actions teams-hero-actions">
            <a class="competitions-button competitions-button-primary" href="/competitions">返回比赛中心</a>
            <a class="competitions-button competitions-button-secondary" href="${escapeHtml(payload.legacy_href || "/teams/legacy")}">查看旧版战队页</a>
          </div>
        </section>
        ${renderMetrics(payload.metrics)}
        <section class="competitions-panel competitions-section teams-section">
          <div class="competitions-section-head">
            <div>
              <div class="competitions-section-kicker">Team Ranking</div>
              <h2 class="competitions-section-title">战队列表</h2>
              <p class="competitions-section-copy">按当前积分排行展示，点击卡片进入战队详情页。</p>
            </div>
            <span class="competitions-chip is-active">${escapeHtml(scope.label || "当前范围")}</span>
          </div>
          ${renderTeams(payload.teams)}
        </section>
      </div>
    `;
    const seasonSwitcher = root.querySelector("[data-season-switcher]");
    if (seasonSwitcher) {
      seasonSwitcher.addEventListener("change", (event) => {
        if (event.currentTarget.value) window.location.href = event.currentTarget.value;
      });
    }
  }

  function renderError(message) {
    root.innerHTML = `
      <section class="competitions-error-shell">
        <div class="competitions-loading-kicker">Load Failed</div>
        <h1>战队中心加载失败</h1>
        <p>${escapeHtml(message)}</p>
      </section>
    `;
  }

  async function loadTeams() {
    const endpoint = `${bootstrap.apiEndpoint || "/api/teams"}${window.location.search || ""}`;
    try {
      const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      renderDashboard(await response.json());
    } catch (error) {
      renderError(error instanceof Error ? error.message : "unknown error");
    }
  }

  loadTeams();
})();
