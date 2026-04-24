(function () {
  const bootstrap = window.__WEREWOLF_PLAYERS_BOOTSTRAP__ || {};
  const root = document.getElementById("players-app");
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
      <section class="competitions-metrics-grid players-metrics-grid">
        ${items.map((item) => `
          <article class="competitions-metric players-metric-card">
            <div class="competitions-stat-label">${escapeHtml(item.label)}</div>
            <div class="competitions-metric-value">${escapeHtml(item.value)}</div>
            <div class="competitions-meta-text">${escapeHtml(item.copy)}</div>
          </article>
        `).join("")}
      </section>
    `;
  }

  function renderPlayers(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return `
        <div class="competitions-empty-state">
          <div class="competitions-card-kicker">Players Empty</div>
          <h3>当前范围还没有选手</h3>
          <p>可以先进入后台维护选手，或切换到其他赛区/赛事查看。</p>
        </div>
      `;
    }
    return `
      <div class="players-grid">
        ${items.map((player) => `
          <a class="competitions-card players-card" href="${escapeHtml(player.href)}">
            <div class="players-card-head">
              <span class="players-rank">#${escapeHtml(player.rank)}</span>
              <img class="players-avatar" src="${escapeHtml(player.photo)}" alt="${escapeHtml(player.display_name)}">
              <div class="players-title-block">
                <h3 class="competitions-card-title players-title">${escapeHtml(player.display_name)}</h3>
                <div class="competitions-meta-text">${escapeHtml(player.team_name || "未绑定战队")}</div>
              </div>
            </div>
            <div class="players-score-row">
              <div><span>积分</span><strong>${escapeHtml(player.points_total)}</strong></div>
              <div><span>胜率</span><strong>${escapeHtml(player.win_rate)}</strong></div>
              <div><span>出场</span><strong>${escapeHtml(player.games_played)} 局</strong></div>
            </div>
            <div class="players-meta-row">
              <span>${escapeHtml(player.record)} 战绩</span>
              <span>均分 ${escapeHtml(player.average_points)}</span>
              <span>站边 ${escapeHtml(player.stance_rate)}</span>
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
      <div class="competitions-layout players-layout">
        ${renderAlert(bootstrap.alert)}
        <section class="competitions-panel competitions-hero-main players-hero">
          <div class="competitions-section-kicker">Players Center</div>
          <h1 class="competitions-title">选手中心</h1>
          <p class="competitions-copy">${escapeHtml(scope.description || "查看当前赛区和赛事范围下的选手积分、胜率和出场情况。")}</p>
          <div class="competitions-filter-grid players-filter-grid">
            <section class="competitions-filter-card"><div class="competitions-filter-label">赛区切换</div>${renderChipLinks(filters.regions)}</section>
            <section class="competitions-filter-card"><div class="competitions-filter-label">系列赛切换</div>${renderChipLinks(filters.series)}</section>
            <section class="competitions-filter-card"><div class="competitions-filter-label">赛事切换</div>${renderChipLinks(filters.competitions)}</section>
            <section class="competitions-filter-card"><div class="competitions-filter-label">赛季切换</div>${renderSeasonSelect(filters.seasons)}</section>
          </div>
          <div class="competitions-card-actions players-hero-actions">
            <a class="competitions-button competitions-button-primary" href="/competitions">返回比赛中心</a>
            <a class="competitions-button competitions-button-secondary" href="/teams">查看战队中心</a>
          </div>
        </section>
        ${renderMetrics(payload.metrics)}
        <section class="competitions-panel competitions-section players-section">
          <div class="competitions-section-head">
            <div>
              <div class="competitions-section-kicker">Player Ranking</div>
              <h2 class="competitions-section-title">选手列表</h2>
              <p class="competitions-section-copy">按当前积分排行展示，点击卡片进入选手详情页。</p>
            </div>
            <span class="competitions-chip is-active">${escapeHtml(scope.label || "当前范围")}</span>
          </div>
          ${renderPlayers(payload.players)}
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
        <h1>选手中心加载失败</h1>
        <p>${escapeHtml(message)}</p>
      </section>
    `;
  }

  async function loadPlayers() {
    const endpoint = `${bootstrap.apiEndpoint || "/api/players"}${window.location.search || ""}`;
    try {
      const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      renderDashboard(await response.json());
    } catch (error) {
      renderError(error instanceof Error ? error.message : "unknown error");
    }
  }

  loadPlayers();
})();
