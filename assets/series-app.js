(function () {
  const bootstrap = window.__WEREWOLF_SERIES_BOOTSTRAP__ || {};
  const root = document.getElementById("series-app");

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

  function renderSeasonSelect(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return '<div class="competitions-chip-empty">当前系列赛还没有赛季可切换。</div>';
    }
    return `
      <select class="competitions-select" data-series-season-switcher>
        ${items
          .map(
            (item) => `
              <option value="${escapeHtml(item.href)}"${item.selected ? " selected" : ""}>
                ${escapeHtml(item.label)}
              </option>
            `
          )
          .join("")}
      </select>
    `;
  }

  function renderMetrics(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return "";
    }
    return `
      <section class="competitions-metrics-grid">
        ${items
          .map(
            (item) => `
              <article class="competitions-metric">
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

  function renderCards(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return `
        <div class="competitions-empty-state">
          <div class="competitions-panel-kicker">Empty</div>
          <h3>该系列赛还没有地区赛事入口</h3>
          <p class="competitions-empty-copy">可以先维护系列赛目录，或者继续补录地区赛事数据。</p>
        </div>
      `;
    }
    return `
      <div class="competitions-card-grid">
        ${items
          .map(
            (item) => `
              <article class="competitions-card">
                <div>
                  <div class="competitions-card-kicker">${escapeHtml(item.region_name)} · Regional Event</div>
                  <h3 class="competitions-card-title">${escapeHtml(item.competition_name)}</h3>
                  <div class="competitions-meta-text">赛季 ${(item.seasons || [])
                    .map((season) => escapeHtml(season))
                    .join("、") || "待录入"}</div>
                  <div class="competitions-meta-text">最近比赛日 ${escapeHtml(item.latest_played_on)}</div>
                  <p class="competitions-card-copy">从这里进入该地区赛事页，继续查看该赛季的战队、比赛日和榜单详情。</p>
                </div>
                <div class="competitions-card-stat-grid">
                  <div class="competitions-card-stat"><span>战队</span><strong>${escapeHtml(item.team_count)} 支</strong></div>
                  <div class="competitions-card-stat"><span>队员</span><strong>${escapeHtml(item.player_count)} 名</strong></div>
                  <div class="competitions-card-stat"><span>对局</span><strong>${escapeHtml(item.match_count)} 场</strong></div>
                </div>
                <div class="competitions-card-actions">
                  <a class="competitions-button competitions-button-primary" href="${escapeHtml(
                    item.competition_href
                  )}">进入地区赛事页</a>
                </div>
              </article>
            `
          )
          .join("")}
      </div>
    `;
  }

  function renderSeries(payload) {
    const hero = payload.hero || {};
    const filters = payload.filters || {};
    const management = payload.management || {};
    root.innerHTML = `
      <div class="competitions-layout">
        ${renderAlert(payload.alert || bootstrap.alert)}
        <section class="competitions-hero">
          <article class="competitions-panel competitions-hero-main">
            <div class="competitions-section-kicker">Series Frontend</div>
            <h1 class="competitions-title">${escapeHtml(hero.title || "系列专题页")}</h1>
            <p class="competitions-copy">${escapeHtml(hero.copy || "")}</p>
            <div class="competitions-filter-grid">
              <section class="competitions-filter-card">
                <div class="competitions-filter-label">赛季切换</div>
                ${renderSeasonSelect(filters.seasons)}
              </section>
            </div>
            <div class="competitions-hero-actions">
              ${
                management.can_manage_series
                  ? `<a class="competitions-button competitions-button-primary" href="${escapeHtml(
                      management.manage_href
                    )}">维护系列赛目录</a>`
                  : ""
              }
              <a class="competitions-button competitions-button-secondary" href="${escapeHtml(
                payload.back_href || "/competitions"
              )}">返回首页</a>
              <a class="competitions-button competitions-button-secondary" href="${escapeHtml(
                payload.legacy_href || "#"
              )}">查看旧版专题页</a>
            </div>
          </article>
          <aside class="competitions-panel competitions-hero-side">
            <div class="competitions-panel-kicker">Season Entry</div>
            <h2 class="competitions-section-title">${escapeHtml(hero.selected_season || "全部赛季")}</h2>
            <p class="competitions-copy">${escapeHtml(hero.region_copy || "")}</p>
            <div class="competitions-sidebar-grid">
              <div class="competitions-side-metric">
                <div class="competitions-stat-label">最近比赛日</div>
                <strong>${escapeHtml(hero.latest_played_on || "待更新")}</strong>
                <div class="competitions-meta-text">${escapeHtml(hero.latest_copy || "当前专题口径")}</div>
              </div>
            </div>
          </aside>
        </section>
        ${renderMetrics(payload.metrics || [])}
        <section class="competitions-panel competitions-section">
          <div class="competitions-section-head">
            <div>
              <div class="competitions-section-kicker">Regional Events</div>
              <h2 class="competitions-section-title">地区赛事页入口</h2>
              <p class="competitions-copy">系列专题页只保留赛季和地区入口，具体赛程、榜单和 AI 总结继续进入地区赛事页查看。</p>
            </div>
          </div>
          ${renderCards(payload.cards)}
        </section>
      </div>
    `;

    const select = root.querySelector("[data-series-season-switcher]");
    if (select) {
      select.addEventListener("change", function () {
        if (select.value) {
          window.location.href = select.value;
        }
      });
    }
  }

  function renderError(message) {
    root.innerHTML = `
      <section class="competitions-error-shell">
        <div class="competitions-loading-kicker">Load Failed</div>
        <h1>系列专题页加载失败</h1>
        <p>${escapeHtml(message)}</p>
        <p><a class="competitions-inline-link" href="${escapeHtml(
          bootstrap.legacyHref || "/competitions"
        )}">可以先打开旧版页面继续使用</a></p>
      </section>
    `;
  }

  async function loadSeries() {
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
      renderSeries(payload);
    } catch (error) {
      renderError(error instanceof Error ? error.message : "unknown error");
    }
  }

  loadSeries();
})();
