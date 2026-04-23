(function () {
  const bootstrap = window.__WEREWOLF_GUILDS_BOOTSTRAP__ || {};
  const root = document.getElementById("guilds-app");

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
    return `<div class="guilds-alert">${escapeHtml(message)}</div>`;
  }

  function renderMetrics(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return "";
    }
    return `
      <section class="guilds-metrics-grid">
        ${items
          .map(
            (item) => `
              <article class="guilds-metric-card">
                <span class="guilds-metric-label">${escapeHtml(item.label)}</span>
                <strong class="guilds-metric-value">${escapeHtml(item.value)}</strong>
                <small class="guilds-metric-copy">${escapeHtml(item.copy)}</small>
              </article>
            `
          )
          .join("")}
      </section>
    `;
  }

  function renderHero(payload) {
    const hero = payload.hero || {};
    const featured = hero.featured;
    const management = payload.management || {};
    return `
      <section class="guilds-hero">
        <article class="guilds-panel guilds-hero-main">
          <div class="guilds-section-kicker">Guild Directory</div>
          <h1 class="guilds-title">${escapeHtml(hero.title || "全部门派")}</h1>
          <p class="guilds-copy">${escapeHtml(hero.copy || "")}</p>
          <div class="guilds-hero-actions">
            <a class="guilds-button guilds-button-primary" href="${escapeHtml(
              management.href || "/profile"
            )}">${escapeHtml(management.label || "进入个人中心")}</a>
            <a class="guilds-button guilds-button-secondary" href="${escapeHtml(
              payload.legacy_href || "/guilds/legacy"
            )}">查看旧版门派页</a>
          </div>
          <p class="guilds-note">${escapeHtml(management.copy || "")}</p>
        </article>
        <aside class="guilds-panel guilds-hero-side">
          <div class="guilds-panel-kicker">Featured Guild</div>
          ${
            featured
              ? `
                <h2 class="guilds-featured-title">${escapeHtml(featured.name)}</h2>
                <div class="guilds-featured-short">${escapeHtml(featured.short_name)}</div>
                <p class="guilds-copy">${escapeHtml(featured.notes)}</p>
                <div class="guilds-featured-grid">
                  <div class="guilds-side-metric">
                    <span>进行中赛季战队</span>
                    <strong>${escapeHtml(featured.ongoing_team_count)}</strong>
                  </div>
                  <div class="guilds-side-metric">
                    <span>比赛</span>
                    <strong>${escapeHtml(featured.match_count)}</strong>
                  </div>
                  <div class="guilds-side-metric">
                    <span>荣誉</span>
                    <strong>${escapeHtml(featured.honor_count)}</strong>
                  </div>
                  <div class="guilds-side-metric">
                    <span>累计赛季战队</span>
                    <strong>${escapeHtml(featured.team_count)}</strong>
                  </div>
                </div>
                <a class="guilds-button guilds-button-secondary" href="${escapeHtml(
                  featured.href
                )}">查看门派详情</a>
              `
              : `
                <h2 class="guilds-featured-title">等待录入门派</h2>
                <p class="guilds-copy">当前还没有可展示的门派数据，登录后可以前往个人中心继续维护。</p>
              `
          }
        </aside>
      </section>
    `;
  }

  function renderCards(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return `
        <div class="guilds-empty-state">
          <div class="guilds-panel-kicker">Empty</div>
          <h3>当前还没有门派</h3>
          <p>可以先去个人中心创建门派，或者等赛事数据继续沉淀后再整理长期组织。</p>
        </div>
      `;
    }
    return `
      <div class="guilds-card-grid">
        ${items
          .map(
            (item) => `
              <article class="guilds-card">
                <div>
                  <div class="guilds-card-kicker">Guild</div>
                  <h3 class="guilds-card-title">${escapeHtml(item.name)}</h3>
                  <div class="guilds-card-short">${escapeHtml(item.short_name)}</div>
                  <p class="guilds-card-copy">${escapeHtml(item.notes)}</p>
                </div>
                <div class="guilds-card-stat-grid">
                  <div class="guilds-card-stat">
                    <span>进行中</span>
                    <strong>${escapeHtml(item.ongoing_team_count)}</strong>
                  </div>
                  <div class="guilds-card-stat">
                    <span>比赛</span>
                    <strong>${escapeHtml(item.match_count)}</strong>
                  </div>
                  <div class="guilds-card-stat">
                    <span>历届战队</span>
                    <strong>${escapeHtml(item.historical_team_count)}</strong>
                  </div>
                  <div class="guilds-card-stat">
                    <span>荣誉</span>
                    <strong>${escapeHtml(item.honor_count)}</strong>
                  </div>
                </div>
                <div class="guilds-card-meta">
                  <span>门主账号 ${escapeHtml(item.leader_username)}</span>
                  <span>累计赛季战队 ${escapeHtml(item.team_count)} 支</span>
                </div>
                <div class="guilds-card-actions">
                  <a class="guilds-button guilds-button-primary" href="${escapeHtml(item.href)}">查看门派详情</a>
                  ${
                    item.manage_href
                      ? `<a class="guilds-button guilds-button-secondary" href="${escapeHtml(
                          item.manage_href
                        )}">进入管理页</a>`
                      : ""
                  }
                </div>
              </article>
            `
          )
          .join("")}
      </div>
    `;
  }

  function renderGuilds(payload) {
    root.innerHTML = `
      <div class="guilds-layout">
        ${renderAlert(payload.alert || bootstrap.alert)}
        ${renderHero(payload)}
        ${renderMetrics(payload.metrics)}
        <section class="guilds-panel guilds-section">
          <div class="guilds-section-head">
            <div>
              <div class="guilds-section-kicker">All Guilds</div>
              <h2 class="guilds-section-title">门派总览</h2>
              <p class="guilds-copy">先从列表浏览长期组织，再下钻到单个门派页查看赛季战队、历届荣誉和审核入口。</p>
            </div>
          </div>
          ${renderCards(payload.cards)}
        </section>
      </div>
    `;
  }

  function renderError(message) {
    root.innerHTML = `
      <section class="guilds-error-shell">
        <div class="guilds-loading-kicker">Load Failed</div>
        <h1>门派列表加载失败</h1>
        <p>${escapeHtml(message)}</p>
        <p><a class="guilds-inline-link" href="/guilds/legacy">可以先打开旧版门派页继续使用</a></p>
      </section>
    `;
  }

  async function loadGuilds() {
    const endpoint = `${bootstrap.apiEndpoint || "/api/guilds"}${window.location.search || ""}`;
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
      renderGuilds(payload);
    } catch (error) {
      renderError(error instanceof Error ? error.message : "unknown error");
    }
  }

  loadGuilds();
})();
