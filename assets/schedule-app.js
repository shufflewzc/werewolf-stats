(function () {
  const bootstrap = window.__WEREWOLF_SCHEDULE_BOOTSTRAP__ || {};
  const root = document.getElementById("schedule-app");
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
      return '<div class="competitions-chip-empty">当前赛事还没有赛季可切换。</div>';
    }
    return `
      <select class="competitions-select" data-schedule-season-switcher>
        ${items.map((item) => `<option value="${escapeHtml(item.href)}"${item.selected ? " selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}
      </select>
    `;
  }

  function renderMetrics(items) {
    if (!Array.isArray(items)) return "";
    return `
      <section class="competitions-metrics-grid schedule-metrics-grid">
        ${items.map((item) => `
          <article class="competitions-metric schedule-metric-card">
            <div class="competitions-stat-label">${escapeHtml(item.label)}</div>
            <div class="competitions-metric-value">${escapeHtml(item.value)}</div>
            <div class="competitions-meta-text">${escapeHtml(item.copy)}</div>
          </article>
        `).join("")}
      </section>
    `;
  }

  function renderCalendarStrip(items) {
    if (!Array.isArray(items) || items.length === 0) return "";
    return `
      <div class="schedule-calendar-strip">
        ${items.map((section, index) => `
          <a class="schedule-date-pill${index === 0 ? " is-next" : ""}" href="${escapeHtml(section.day_href)}">
            <span>${escapeHtml(section.played_on.slice(5))}</span>
            <strong>${escapeHtml((section.rows || []).length)} 场</strong>
          </a>
        `).join("")}
      </div>
    `;
  }

  function renderMatchCard(row) {
    return `
      <a class="schedule-match-card" href="${escapeHtml(row.detail_href)}">
        <div class="schedule-match-main">
          <span class="schedule-match-id">${escapeHtml(row.match_id)}</span>
          <strong>${escapeHtml(row.stage_label)} · ${escapeHtml(row.round_label)} ${escapeHtml(row.game_label || "")}</strong>
          <small>${escapeHtml(row.table_label || "赛程详情")}</small>
        </div>
        <div class="schedule-match-meta">
          <span>${escapeHtml(row.format_label)}</span>
        </div>
      </a>
    `;
  }

  function renderDaySections(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return `
        <div class="competitions-empty-state">
          <div class="competitions-card-kicker">Schedule Empty</div>
          <h3>当前范围还没有赛程</h3>
          <p>可以切换赛事或赛季查看其他比赛日。</p>
        </div>
      `;
    }
    return `
      <section class="competitions-panel competitions-section schedule-section">
        <div class="competitions-section-head">
          <div>
            <div class="competitions-section-kicker">Match Calendar</div>
            <h2 class="competitions-section-title">比赛日列表</h2>
            <p class="competitions-section-copy">按日期从早到晚排列，每个比赛日内展示赛段、轮次和局数。</p>
          </div>
        </div>
        <div class="schedule-days-grid">
          ${items.map((section, index) => `
            <article class="schedule-day-card${index === 0 ? " is-next" : ""}">
              <div class="schedule-day-head">
                <a class="schedule-day-date" href="${escapeHtml(section.day_href)}">${escapeHtml(section.played_on)}</a>
                <span>${escapeHtml((section.rows || []).length)} 场</span>
              </div>
              <p>${escapeHtml(section.copy)}</p>
              <div class="schedule-match-list">
                ${(section.rows || []).map(renderMatchCard).join("")}
              </div>
            </article>
          `).join("")}
        </div>
      </section>
    `;
  }

  function renderSchedule(payload) {
    const hero = payload.hero || {};
    const filters = payload.filters || {};
    const side = payload.hero_side || {};
    const actions = payload.actions || {};
    const days = payload.days || [];
    root.innerHTML = `
      <div class="competitions-layout schedule-layout">
        ${renderAlert(payload.alert || bootstrap.alert)}
        <section class="competitions-panel competitions-hero-main schedule-hero">
          <div class="competitions-section-kicker">Schedule Calendar</div>
          <h1 class="competitions-title">${escapeHtml(hero.title || "赛程日历")}</h1>
          <p class="competitions-copy">${escapeHtml(hero.copy || "按比赛日查看当前赛事赛程。")}</p>
          <div class="schedule-hero-meta">
            <span>${escapeHtml(hero.competition_name || "当前赛事")}</span>
            <span>${escapeHtml(hero.selected_season || "当前赛季")}</span>
            <span>${escapeHtml(side.first_day || "-")} → ${escapeHtml(side.last_day || "-")}</span>
          </div>
          <div class="competitions-filter-grid schedule-filter-grid">
            <section class="competitions-filter-card"><div class="competitions-filter-label">赛事切换</div>${renderChipLinks(filters.competitions)}</section>
            <section class="competitions-filter-card"><div class="competitions-filter-label">赛季切换</div>${renderSeasonSelect(filters.seasons)}</section>
          </div>
          ${renderCalendarStrip(days)}
          <div class="competitions-card-actions schedule-hero-actions">
            <a class="competitions-button competitions-button-secondary" href="${escapeHtml(actions.back_href || "/competitions")}">返回赛事页</a>
            ${actions.create_match_href ? `<a class="competitions-button competitions-button-primary" href="${escapeHtml(actions.create_match_href)}">比赛管理</a>` : ""}
            <a class="competitions-button competitions-button-secondary" href="${escapeHtml(payload.legacy_href || "/schedule/legacy")}">查看旧版场次页</a>
          </div>
        </section>
        ${renderMetrics(payload.metrics || [])}
        ${renderDaySections(days)}
      </div>
    `;

    const select = root.querySelector("[data-schedule-season-switcher]");
    if (select) {
      select.addEventListener("change", function () {
        if (select.value) window.location.href = select.value;
      });
    }
  }

  function renderError(message) {
    root.innerHTML = `
      <section class="competitions-error-shell">
        <div class="competitions-loading-kicker">Load Failed</div>
        <h1>赛程日历加载失败</h1>
        <p>${escapeHtml(message)}</p>
      </section>
    `;
  }

  async function loadSchedule() {
    const endpoint = `${bootstrap.apiEndpoint || "/api/schedule"}${window.location.search || ""}`;
    try {
      const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      renderSchedule(await response.json());
    } catch (error) {
      renderError(error instanceof Error ? error.message : "unknown error");
    }
  }

  loadSchedule();
})();
