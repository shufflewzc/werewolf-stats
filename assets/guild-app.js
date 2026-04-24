(function () {
  const bootstrap = window.__WEREWOLF_GUILD_BOOTSTRAP__ || {};
  const root = document.getElementById("guild-app");
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
    return message ? `<div class="guilds-alert">${escapeHtml(message)}</div>` : "";
  }

  function renderMetrics(items) {
    if (!Array.isArray(items) || items.length === 0) return "";
    return `
      <section class="guilds-metrics-grid guild-detail-metrics-grid">
        ${items.map((item) => `
          <article class="guilds-metric-card">
            <span class="guilds-metric-label">${escapeHtml(item.label)}</span>
            <strong class="guilds-metric-value">${escapeHtml(item.value)}</strong>
            <small class="guilds-metric-copy">${escapeHtml(item.copy)}</small>
          </article>
        `).join("")}
      </section>
    `;
  }

  function renderTeamCard(team) {
    return `
      <a class="guild-detail-team-card" href="${escapeHtml(team.href)}">
        <div>
          <div class="guilds-card-kicker">${escapeHtml(team.status_label)}</div>
          <h3 class="guilds-card-title">${escapeHtml(team.team_name)}</h3>
          <p class="guilds-card-copy">${escapeHtml(team.competition_name)} · ${escapeHtml(team.season_name)}</p>
        </div>
        <div class="guild-detail-team-stats">
          <div><span>对局</span><strong>${escapeHtml(team.matches)}</strong></div>
          <div><span>队员</span><strong>${escapeHtml(team.player_count)}</strong></div>
          <div><span>总积分</span><strong>${escapeHtml(team.points_total)}</strong></div>
        </div>
      </a>
    `;
  }

  function renderOngoingTeams(items) {
    return `
      <section class="guilds-panel guilds-section guild-detail-section">
        <div class="guilds-section-head">
          <div>
            <div class="guilds-section-kicker">Active Teams</div>
            <h2 class="guilds-section-title">当前进行中的赛季战队</h2>
            <p class="guilds-copy">这里只展示已经加入该门派、且所在赛季仍在进行中的战队。</p>
          </div>
        </div>
        ${Array.isArray(items) && items.length ? `<div class="guild-detail-team-grid">${items.map(renderTeamCard).join("")}</div>` : `
          <div class="guilds-empty-state">
            <div class="guilds-panel-kicker">Empty</div>
            <h3>暂无进行中的赛季战队</h3>
            <p>该门派当前没有进行中的赛季战队。</p>
          </div>
        `}
      </section>
    `;
  }

  function renderHistory(sections) {
    if (!Array.isArray(sections) || sections.length === 0) return "";
    return `
      <section class="guilds-panel guilds-section guild-detail-section">
        <div class="guilds-section-head">
          <div>
            <div class="guilds-section-kicker">Archive</div>
            <h2 class="guilds-section-title">历届赛季战队</h2>
            <p class="guilds-copy">按赛事聚合展示该门派的历史赛季身份和积分记录。</p>
          </div>
        </div>
        <div class="guild-detail-history-stack">
          ${sections.map((section) => `
            <details class="guild-detail-history-card">
              <summary>
                <span>${escapeHtml(section.competition_name)}</span>
                <small>${escapeHtml(section.team_count)} 支 · 总积分 ${escapeHtml(section.points_total)}</small>
              </summary>
              <div class="guild-detail-table-wrap">
                <table class="guild-detail-table">
                  <thead><tr><th>赛季</th><th>战队</th><th>状态</th><th>队员</th><th>对局</th><th>总积分</th><th>操作</th></tr></thead>
                  <tbody>
                    ${(section.rows || []).map((row) => `
                      <tr>
                        <td>${escapeHtml(row.season_name)}</td>
                        <td>${escapeHtml(row.team_name)}</td>
                        <td>${escapeHtml(row.status_label)}</td>
                        <td>${escapeHtml(row.player_count)}</td>
                        <td>${escapeHtml(row.matches)}</td>
                        <td>${escapeHtml(row.points_total)}</td>
                        <td><a class="guilds-button guilds-button-secondary" href="${escapeHtml(row.href)}">查看详情</a></td>
                      </tr>
                    `).join("")}
                  </tbody>
                </table>
              </div>
            </details>
          `).join("")}
        </div>
      </section>
    `;
  }

  function renderHonors(items) {
    return `
      <section class="guilds-panel guilds-section guild-detail-section">
        <div class="guilds-section-head">
          <div>
            <div class="guilds-section-kicker">Honors</div>
            <h2 class="guilds-section-title">历届荣誉</h2>
          </div>
        </div>
        ${Array.isArray(items) && items.length ? `
          <div class="guild-detail-honor-grid">
            ${items.map((item) => `
              <article class="guild-detail-honor-card">
                <div class="guilds-card-kicker">${escapeHtml(item.scope)}</div>
                <h3 class="guilds-card-title">${escapeHtml(item.title)}</h3>
                <p class="guilds-card-copy">${escapeHtml(item.team_name)}</p>
              </article>
            `).join("")}
          </div>
        ` : `
          <div class="guilds-empty-state">
            <div class="guilds-panel-kicker">Honors Empty</div>
            <h3>暂无荣誉归档</h3>
            <p>当前还没有可归档的荣誉。</p>
          </div>
        `}
      </section>
    `;
  }

  function renderManagement(payload) {
    if (!payload.manage_mode) return "";
    const guild = payload.guild || {};
    const pending = payload.pending_requests || [];
    return `
      <section class="guilds-panel guilds-section guild-detail-section guild-detail-manage-section">
        <div class="guilds-section-head">
          <div>
            <div class="guilds-section-kicker">Management</div>
            <h2 class="guilds-section-title">门派管理</h2>
            <p class="guilds-copy">${escapeHtml((payload.management || {}).source_copy || "门派管理入口。")}</p>
          </div>
        </div>
        ${payload.can_manage_honors ? `
          <form method="post" action="${escapeHtml(payload.manage_post_path || "")}" class="guild-detail-form">
            <input type="hidden" name="action" value="update_guild_honors">
            <label>历届荣誉维护</label>
            <textarea name="honors_text" rows="7" placeholder="全国总冠军 | 狼王战队 | 2025 全国总决赛">${escapeHtml(guild.honors_text || "")}</textarea>
            <button type="submit" class="guilds-button guilds-button-primary">保存历届荣誉</button>
          </form>
        ` : ""}
        ${payload.can_manage_membership && pending.length ? `
          <div class="guild-detail-table-wrap guild-detail-pending-wrap">
            <table class="guild-detail-table">
              <thead><tr><th>战队</th><th>赛事赛季</th><th>申请账号</th><th>申请时间</th><th>操作</th></tr></thead>
              <tbody>
                ${pending.map((item) => `
                  <tr>
                    <td>${escapeHtml(item.team_name)}</td>
                    <td>${escapeHtml(item.scope)}</td>
                    <td>${escapeHtml(item.username)}</td>
                    <td>${escapeHtml(item.created_on)}</td>
                    <td>
                      <div class="guild-detail-action-row">
                        <form method="post" action="${escapeHtml(payload.manage_post_path || "")}">
                          <input type="hidden" name="action" value="approve_guild_join">
                          <input type="hidden" name="request_id" value="${escapeHtml(item.request_id)}">
                          <button type="submit" class="guilds-button guilds-button-primary">通过</button>
                        </form>
                        <form method="post" action="${escapeHtml(payload.manage_post_path || "")}">
                          <input type="hidden" name="action" value="reject_guild_join">
                          <input type="hidden" name="request_id" value="${escapeHtml(item.request_id)}">
                          <button type="submit" class="guilds-button guilds-button-secondary">拒绝</button>
                        </form>
                      </div>
                    </td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          </div>
        ` : ""}
      </section>
    `;
  }

  function renderGuild(payload) {
    const guild = payload.guild || {};
    if (payload.title) document.title = payload.title;
    root.innerHTML = `
      <div class="guilds-layout guild-detail-layout">
        ${renderAlert(payload.alert || bootstrap.alert)}
        <section class="guilds-hero guild-detail-hero">
          <article class="guilds-panel guilds-hero-main">
            <div class="guilds-section-kicker">${payload.manage_mode ? "Guild Management" : "Guild Detail"}</div>
            <h1 class="guilds-title">${escapeHtml(guild.name || "门派详情")}</h1>
            <p class="guilds-copy">${escapeHtml(guild.notes || "门派长期存在，可跨赛季组织多支战队。")}</p>
            <div class="guild-detail-meta-row">
              <span>${escapeHtml(guild.short_name || "未设置简称")}</span>
              <span>门主账号 ${escapeHtml(guild.leader_username || "未设置")}</span>
              <span>${escapeHtml(payload.generated_at || "")}</span>
            </div>
            <div class="guilds-hero-actions">
              <a class="guilds-button guilds-button-secondary" href="${escapeHtml((payload.management || {}).back_href || "/guilds")}">返回门派列表</a>
              <a class="guilds-button guilds-button-secondary" href="${escapeHtml((payload.management || {}).profile_href || "/profile")}">进入个人中心</a>
              ${payload.manage_mode ? `<a class="guilds-button guilds-button-primary" href="${escapeHtml(payload.public_href || "#")}">查看对外页面</a>` : (payload.manage_href ? `<a class="guilds-button guilds-button-primary" href="${escapeHtml(payload.manage_href)}">管理门派</a>` : "")}
              <a class="guilds-button guilds-button-secondary" href="${escapeHtml(payload.legacy_href || bootstrap.legacyHref || "#")}">查看旧版</a>
            </div>
          </article>
        </section>
        ${renderMetrics(payload.metrics)}
        ${renderManagement(payload)}
        ${renderOngoingTeams(payload.ongoing_teams || [])}
        ${renderHistory(payload.history_sections || [])}
        ${renderHonors(payload.honors || [])}
      </div>
    `;
  }

  function renderError(message, legacyHref) {
    root.innerHTML = `
      <section class="guilds-error-shell">
        <div class="guilds-loading-kicker">Load Failed</div>
        <h1>门派详情加载失败</h1>
        <p>${escapeHtml(message || "unknown error")}</p>
        <p><a class="guilds-inline-link" href="${escapeHtml(legacyHref || bootstrap.legacyHref || "/guilds")}">打开旧版门派页</a></p>
      </section>
    `;
  }

  async function loadGuildPage() {
    const endpoint = `${bootstrap.apiEndpoint || ""}${window.location.search || ""}`;
    try {
      const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
      const payload = await response.json();
      if (!response.ok || payload.error) {
        throw Object.assign(new Error(payload.error || `HTTP ${response.status}`), { payload });
      }
      renderGuild(payload);
    } catch (error) {
      renderError(error instanceof Error ? error.message : "unknown error", error && error.payload && error.payload.legacy_href);
    }
  }

  loadGuildPage();
})();
