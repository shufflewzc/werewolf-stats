(function () {
  const bootstrap = window.__WEREWOLF_SCHEDULE_BOOTSTRAP__ || {};
  const root = document.getElementById("schedule-app");

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

  function renderChipLinks(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return '<div class="competitions-chip-empty">当前没有可切换的选项。</div>';
    }
    return `
      <div class="competitions-chip-list">
        ${items
          .map(
            (item) => `
              <a class="competitions-chip${item.active ? " is-active" : ""}" href="${escapeHtml(item.href)}">
                ${escapeHtml(item.label)}
              </a>
            `
          )
          .join("")}
      </div>
    `;
  }

  function renderSeasonSelect(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return '<div class="competitions-chip-empty">当前赛事还没有赛季可切换。</div>';
    }
    return `
      <select class="competitions-select" data-schedule-season-switcher>
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
    return `
      <section class="competitions-metrics-grid">
        ${(items || [])
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

  function renderDaySections(items) {
    return (items || [])
      .map(
        (section) => `
          <section class="competitions-panel competitions-section">
            <div class="competitions-section-head">
              <div>
                <div class="competitions-section-kicker">Match Day</div>
                <h2 class="competitions-section-title"><a href="${escapeHtml(section.day_href)}">${escapeHtml(
          section.played_on
        )}</a></h2>
                <p class="competitions-copy">${escapeHtml(section.copy)}</p>
              </div>
            </div>
            <div class="competitions-table-panel">
              <table class="competitions-table">
                <thead>
                  <tr><th>编号</th><th>赛季</th><th>阶段</th><th>轮次</th><th>参赛分组</th><th>房间</th><th>板型</th><th>操作</th></tr>
                </thead>
                <tbody>
                  ${(section.rows || [])
                    .map(
                      (row) => `
                        <tr>
                          <td><a href="${escapeHtml(row.detail_href)}">${escapeHtml(row.match_id)}</a></td>
                          <td>${escapeHtml(row.season_name)}</td>
                          <td>${escapeHtml(row.stage_label)}</td>
                          <td>${escapeHtml(row.round_label)}</td>
                          <td>${escapeHtml(row.group_label)}</td>
                          <td>${escapeHtml(row.table_label)}</td>
                          <td>${escapeHtml(row.format_label)}</td>
                          <td><a class="competitions-button competitions-button-secondary" href="${escapeHtml(
                            row.detail_href
                          )}">查看详情</a></td>
                        </tr>
                      `
                    )
                    .join("")}
                </tbody>
              </table>
            </div>
          </section>
        `
      )
      .join("");
  }

  function renderSchedule(payload) {
    const hero = payload.hero || {};
    const filters = payload.filters || {};
    const side = payload.hero_side || {};
    const actions = payload.actions || {};
    root.innerHTML = `
      <div class="competitions-layout">
        ${renderAlert(payload.alert || bootstrap.alert)}
        <section class="competitions-hero">
          <article class="competitions-panel competitions-hero-main">
            <div class="competitions-section-kicker">Schedule Frontend</div>
            <h1 class="competitions-title">${escapeHtml(hero.title || "赛事场次页")}</h1>
            <p class="competitions-copy">${escapeHtml(hero.copy || "")}</p>
            <div class="competitions-filter-grid">
              <section class="competitions-filter-card">
                <div class="competitions-filter-label">赛事切换</div>
                ${renderChipLinks(filters.competitions)}
              </section>
              <section class="competitions-filter-card">
                <div class="competitions-filter-label">赛季切换</div>
                ${renderSeasonSelect(filters.seasons)}
              </section>
            </div>
            <div class="competitions-hero-actions">
              <a class="competitions-button competitions-button-secondary" href="${escapeHtml(
                actions.back_href || "/competitions"
              )}">返回赛事页</a>
              ${
                actions.create_match_href
                  ? `<a class="competitions-button competitions-button-primary" href="${escapeHtml(
                      actions.create_match_href
                    )}">比赛管理</a>`
                  : ""
              }
              <a class="competitions-button competitions-button-secondary" href="${escapeHtml(
                payload.legacy_href || "/schedule/legacy"
              )}">查看旧版场次页</a>
            </div>
          </article>
          <aside class="competitions-panel competitions-hero-side">
            <div class="competitions-panel-kicker">All Matches</div>
            <h2 class="competitions-section-title">${escapeHtml(side.season_title || "")}</h2>
            <div class="competitions-sidebar-grid">
              <div class="competitions-side-metric"><div class="competitions-stat-label">首个比赛日</div><strong>${escapeHtml(
                side.first_day || "-"
              )}</strong><div class="competitions-meta-text">当前赛季起始</div></div>
              <div class="competitions-side-metric"><div class="competitions-stat-label">最后比赛日</div><strong>${escapeHtml(
                side.last_day || "-"
              )}</strong><div class="competitions-meta-text">当前赛季截止</div></div>
              <div class="competitions-side-metric"><div class="competitions-stat-label">比赛场次</div><strong>${escapeHtml(
                side.match_count || "0"
              )}</strong><div class="competitions-meta-text">当前赛季全部场次</div></div>
              <div class="competitions-side-metric"><div class="competitions-stat-label">比赛日</div><strong>${escapeHtml(
                side.day_count || "0"
              )}</strong><div class="competitions-meta-text">当前赛季涉及日期</div></div>
            </div>
          </aside>
        </section>
        ${renderMetrics(payload.metrics || [])}
        ${renderDaySections(payload.days || [])}
      </div>
    `;

    const select = root.querySelector("[data-schedule-season-switcher]");
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
        <h1>赛事场次页加载失败</h1>
        <p>${escapeHtml(message)}</p>
      </section>
    `;
  }

  async function loadSchedule() {
    const endpoint = `${bootstrap.apiEndpoint || "/api/schedule"}${window.location.search || ""}`;
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
      renderSchedule(payload);
    } catch (error) {
      renderError(error instanceof Error ? error.message : "unknown error");
    }
  }

  loadSchedule();
})();
