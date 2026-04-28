(function () {
  const bootstrap = window.__WEREWOLF_PLAYER_BOOTSTRAP__ || {};
  const root = document.getElementById("player-app");

  if (!root) return;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function width(value) {
    const number = Number(value || 0);
    return Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : 0;
  }

  function renderAlert(message) {
    return message ? `<div class="competitions-alert">${escapeHtml(message)}</div>` : "";
  }

  function renderMetrics(metrics) {
    return `
      <section class="competitions-metrics-grid player-detail-metrics-grid">
        ${(metrics || []).map((item) => `
          <article class="competitions-metric player-detail-metric">
            <div class="competitions-stat-label">${escapeHtml(item.label)}</div>
            <div class="competitions-stat-value">${escapeHtml(item.value)}</div>
            <p class="competitions-card-copy">${escapeHtml(item.copy || "")}</p>
          </article>
        `).join("")}
      </section>
    `;
  }

  function renderInsight(player, insights) {
    return `
      <aside class="competitions-panel player-detail-insight-card">
        <div>
          <div class="competitions-section-kicker">Player Insight</div>
          <h2 class="competitions-section-title">选手观察</h2>
          <p class="competitions-copy">从综合胜率、好人胜率和狼人胜率看当前筛选范围下的选手倾向。</p>
        </div>
        ${[
          ["综合胜率", insights.overall_win_rate, insights.overall_width],
          ["好人胜率", insights.villagers_win_rate, insights.villagers_width],
          ["狼人胜率", insights.werewolves_win_rate, insights.werewolves_width],
        ].map(([label, value, barWidth]) => `
          <div class="player-detail-meter-row">
            <div class="player-detail-meter-head"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(value)}</span></div>
            <div class="player-detail-meter-track"><div class="player-detail-meter-fill" style="width:${width(barWidth)}%"></div></div>
          </div>
        `).join("")}
        <div class="player-detail-note-grid">
          <div class="player-detail-note-item"><span>Team</span><strong>${escapeHtml(player.team_name || "未加入战队")}</strong></div>
          <div class="player-detail-note-item"><span>Aliases</span><strong>${escapeHtml((player.aliases || []).join("、") || "无")}</strong></div>
          <div class="player-detail-note-item"><span>Joined</span><strong>${escapeHtml(player.joined_on || "未记录")}</strong></div>
          <div class="player-detail-note-item"><span>Owner</span><strong>${escapeHtml(player.owner || "未绑定账号")}</strong></div>
        </div>
      </aside>
    `;
  }

  function renderRoles(roles) {
    const items = Array.isArray(roles) ? roles : [];
    if (!items.length) return `<div class="competitions-empty-state">当前范围内暂无角色记录。</div>`;
    return `
      <div class="player-detail-role-grid">
        ${items.map((item) => `
          <article class="player-detail-role-card">
            <div class="player-detail-role-top">
              <strong>${escapeHtml(item.role)}</strong>
              <span>${escapeHtml(item.games)} 局</span>
            </div>
            <div class="player-detail-meter-track"><div class="player-detail-meter-fill" style="width:${width(item.width)}%"></div></div>
            <p>${escapeHtml(item.share)} · 当前角色占比</p>
          </article>
        `).join("")}
      </div>
    `;
  }

  function renderMatches(matches) {
    const items = Array.isArray(matches) ? matches : [];
    if (!items.length) return `<div class="competitions-empty-state">当前范围内暂无比赛记录。</div>`;
    return `
      <div class="player-detail-match-grid">
        ${items.map((match) => `
          <a class="player-detail-match-card" href="${escapeHtml(match.href || "#")}">
            <div class="player-detail-match-top">
              <span>${escapeHtml(match.played_on || "未定日期")}</span>
              <strong>${escapeHtml(match.result_label || "-")}</strong>
            </div>
            <div class="player-detail-match-title">${escapeHtml(match.stage_label || "赛段")} · 第 ${escapeHtml(match.round || 0)} 轮 第 ${escapeHtml(match.game_no || 0)} 局</div>
            <div class="player-detail-match-meta">
              <span>${escapeHtml(match.role || "未记录角色")}</span>
              <span>${escapeHtml(match.camp_label || "未记录阵营")}</span>
              <span>${escapeHtml(match.points_earned)} 分</span>
              ${(match.award_labels || []).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
            </div>
          </a>
        `).join("")}
      </div>
    `;
  }

  function renderSeasonStats(items) {
    const stats = Array.isArray(items) ? items : [];
    if (!stats.length) return `<div class="competitions-empty-state">当前范围内暂无赛季切片。</div>`;
    return `
      <div class="player-detail-season-grid">
        ${stats.map((item) => `
          <article class="player-detail-season-card">
            <div class="player-detail-season-head">
              <strong>${escapeHtml(item.season_name)}</strong>
              <span>${escapeHtml(item.points_total)} 分</span>
            </div>
            <p>${escapeHtml(item.competition_name)}</p>
            <div class="player-detail-season-stats">
              <span>${escapeHtml(item.games_played)} 局</span>
              <span>${escapeHtml(item.record)}</span>
              <span>${escapeHtml(item.overall_win_rate)}</span>
              <span>场均 ${escapeHtml(item.average_points)}</span>
            </div>
          </article>
        `).join("")}
      </div>
    `;
  }

  function radarPoint(index, ratio, centerX, centerY, radius, total) {
    const angle = -Math.PI / 2 + index * 2 * Math.PI / total;
    return [
      centerX + Math.cos(angle) * radius * ratio,
      centerY + Math.sin(angle) * radius * ratio,
    ];
  }

  function renderRadarHexagon(items) {
    const radar = Array.isArray(items) ? items.slice(0, 6) : [];
    if (radar.length !== 6) return "";
    const centerX = 150;
    const centerY = 142;
    const radius = 86;
    const grid = [0.25, 0.5, 0.75, 1].map((level) => {
      const points = radar.map((_, index) => {
        const [x, y] = radarPoint(index, level, centerX, centerY, radius, radar.length);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(" ");
      return `<polygon points="${points}" fill="none" stroke="rgba(143, 211, 255, ${0.18 + level * 0.18})" stroke-width="1"></polygon>`;
    }).join("");
    const axes = radar.map((item, index) => {
      const [x, y] = radarPoint(index, 1, centerX, centerY, radius, radar.length);
      const [labelX, labelY] = radarPoint(index, 1.28, centerX, centerY, radius, radar.length);
      const anchor = labelX < centerX - 8 ? "end" : labelX > centerX + 8 ? "start" : "middle";
      return `
        <line x1="${centerX}" y1="${centerY}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="rgba(205, 226, 252, 0.18)" stroke-width="1"></line>
        <text x="${labelX.toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="${anchor}" font-size="10.5" font-weight="800" fill="#d7e9ff">${escapeHtml(item.label)}</text>
        <text x="${labelX.toFixed(1)}" y="${(labelY + 14).toFixed(1)}" text-anchor="${anchor}" font-size="10.5" fill="#8fd3ff">${escapeHtml(item.display)}</text>
      `;
    }).join("");
    const dataPoints = radar.map((item, index) => {
      const ratio = Math.max(0, Math.min(1, Number(item.ratio || 0)));
      return radarPoint(index, ratio, centerX, centerY, radius, radar.length);
    });
    const polygon = dataPoints.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
    const points = dataPoints.map(([x, y], index) => `
      <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4" fill="#8fd3ff" stroke="#061426" stroke-width="1.5">
        <title>${escapeHtml(radar[index].label)}：${escapeHtml(radar[index].display)}</title>
      </circle>
    `).join("");
    return `
      <div class="player-detail-radar-hexagon-wrap">
        <svg class="player-detail-radar-hexagon" viewBox="0 0 300 284" role="img" aria-label="赛季维度六边形图">
          <rect x="0" y="0" width="300" height="284" rx="28" fill="rgba(5, 13, 28, 0.58)"></rect>
          ${grid}
          ${axes}
          <polygon points="${polygon}" fill="rgba(143, 211, 255, 0.24)" stroke="#8fd3ff" stroke-width="2.6"></polygon>
          ${points}
          <circle cx="${centerX}" cy="${centerY}" r="2.8" fill="#8fd3ff"></circle>
        </svg>
      </div>
    `;
  }

  function renderDimension(dimension) {
    const data = dimension || {};
    if (!data.available) {
      return `
        <section class="competitions-panel player-detail-section player-detail-dimension-section">
          <div class="competitions-section-head"><div><div class="competitions-section-kicker">Season Dimension</div><h2 class="competitions-section-title">赛季维度补充数据</h2><p class="competitions-copy">${escapeHtml(data.reason || "当前还没有导入对应赛季的维度数据。")}</p></div></div>
        </section>
      `;
    }
    const radar = Array.isArray(data.radar) ? data.radar : [];
    const history = Array.isArray(data.history) ? data.history : [];
    return `
      <section class="competitions-panel player-detail-section player-detail-dimension-section">
        <div class="competitions-section-head">
          <div>
            <div class="competitions-section-kicker">Season Dimension</div>
            <h2 class="competitions-section-title">赛季维度补充数据</h2>
            <p class="competitions-copy">来自比赛日报 Excel 的赛季维度补充数据，展示分赛季汇总和六维画像。</p>
          </div>
          <span class="player-detail-dimension-chip">${escapeHtml(data.selected_season)}</span>
        </div>
        <div class="player-detail-dimension-grid">
          ${(data.summary_cards || []).map((item) => `
            <article class="player-detail-dimension-card">
              <span>${escapeHtml(item.label)}</span>
              <strong>${escapeHtml(item.value)}</strong>
            </article>
          `).join("")}
        </div>
        ${renderRadarHexagon(radar)}
        <div class="player-detail-table-wrap">
          <table class="player-detail-table">
            <thead><tr><th>日期</th><th>座位</th><th>战队</th><th>当日积分</th><th>局数</th><th>胜场</th><th>投票</th><th>投狼</th><th>MVP</th><th>SVP</th><th>背锅</th></tr></thead>
            <tbody>
              ${history.map((item) => `
                <tr><td>${escapeHtml(item.played_on)}</td><td>${escapeHtml(item.seat)}</td><td>${escapeHtml(item.team_name)}</td><td>${escapeHtml(item.daily_points)}</td><td>${escapeHtml(item.games_played)}</td><td>${escapeHtml(item.wins)}</td><td>${escapeHtml(item.vote_count)}</td><td>${escapeHtml(item.vote_wolf_count)}</td><td>${escapeHtml(item.mvp_count)}</td><td>${escapeHtml(item.svp_count)}</td><td>${escapeHtml(item.scapegoat_count)}</td></tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </section>
    `;
  }

  function renderPlayer(payload) {
    const player = payload.player || {};
    const actions = payload.actions || {};
    const scope = payload.scope || {};
    const insights = payload.insights || {};
    if (payload.requires_scope) {
      if (payload.title) document.title = payload.title;
      root.innerHTML = `
        <section class="competitions-panel competitions-empty-state">
          <div class="competitions-section-kicker">Season Required</div>
          <h1 class="competitions-title">请先选择赛事赛季</h1>
          <p class="competitions-copy">${escapeHtml(payload.message || "选手数据属于具体赛事赛季，请先从比赛中心选择赛季后再查看选手。")}</p>
          <div class="competitions-hero-actions player-detail-actions">
            <a class="competitions-button competitions-button-primary" href="${escapeHtml((actions && actions.competitions_href) || "/competitions")}">前往比赛中心</a>
          </div>
        </section>
      `;
      return;
    }
    if (payload.title) document.title = payload.title;
    root.innerHTML = `
      ${renderAlert(payload.alert || bootstrap.alert)}
      <section class="player-detail-hero">
        <div class="player-detail-hero-left">
          <article class="competitions-panel player-detail-hero-main">
            <img class="player-detail-photo" src="${escapeHtml(player.photo || "/assets/players/default-player.svg")}" alt="${escapeHtml(player.name || "选手")} 头像">
            <div class="player-detail-hero-copy">
              <div class="competitions-section-kicker">Season Player</div>
              <h1 class="competitions-title">${escapeHtml(player.name || "赛季选手详情")}</h1>
              <p class="competitions-copy">${escapeHtml(player.notes || "当前赛事赛季内的选手数据。")}</p>
              <div class="player-detail-meta-row">
                <span>${escapeHtml(scope.competition || "全部赛事")}</span>
                <span>${escapeHtml(scope.season || "全部赛季")}</span>
                <span>${escapeHtml(player.team_name || "未加入战队")}</span>
                <span>排名 #${escapeHtml(player.rank || "-")}</span>
              </div>
              <div class="competitions-hero-actions player-detail-actions">
                <a class="competitions-button competitions-button-secondary" href="${escapeHtml(actions.players_href || "/players")}">返回选手列表</a>
                <a class="competitions-button competitions-button-secondary" href="${escapeHtml(actions.team_href || "/teams")}">查看战队</a>
                ${actions.manage_href ? `<a class="competitions-button competitions-button-primary" href="${escapeHtml(actions.manage_href)}">编辑资料</a>` : ""}
                ${actions.binding_href ? `<a class="competitions-button competitions-button-secondary" href="${escapeHtml(actions.binding_href)}">管理绑定</a>` : ""}
                <a class="competitions-button competitions-button-secondary" href="${escapeHtml(actions.legacy_href || bootstrap.legacyHref || "#")}">查看旧版</a>
              </div>
            </div>
          </article>
          ${renderMetrics(payload.metrics)}
        </div>
        ${renderInsight(player, insights)}
      </section>
      <section class="competitions-panel player-detail-section">
        <div class="competitions-section-head"><div><div class="competitions-section-kicker">Roles</div><h2 class="competitions-section-title">角色画像</h2><p class="competitions-copy">按当前赛事赛季统计这名选手最常出现的位置。</p></div></div>
        ${renderRoles(payload.roles)}
      </section>
      <section class="competitions-panel player-detail-section">
        <div class="competitions-section-head"><div><div class="competitions-section-kicker">Recent Matches</div><h2 class="competitions-section-title">最近比赛</h2><p class="competitions-copy">展示最近对局的角色、阵营、结果、得分和奖项。</p></div></div>
        ${renderMatches(payload.recent_matches)}
      </section>
      <section class="competitions-panel player-detail-section">
        <div class="competitions-section-head"><div><div class="competitions-section-kicker">Season Slices</div><h2 class="competitions-section-title">赛季切片</h2><p class="competitions-copy">当前选手身份属于赛事赛季，这里只作为同赛季明细核对。</p></div></div>
        ${renderSeasonStats(payload.season_stats)}
      </section>
      ${renderDimension(payload.dimension)}
    `;
  }

  function renderError(message, legacyHref) {
    root.innerHTML = `
      <section class="competitions-panel competitions-empty-state">
        <div class="competitions-section-kicker">Load Failed</div>
        <h1 class="competitions-title">选手详情加载失败</h1>
        <p class="competitions-copy">${escapeHtml(message || "unknown error")}</p>
        <a class="competitions-button competitions-button-secondary" href="${escapeHtml(legacyHref || bootstrap.legacyHref || "/players")}">打开旧版选手页</a>
      </section>
    `;
  }

  async function loadPlayerPage() {
    const endpoint = `${bootstrap.apiEndpoint || ""}${window.location.search || ""}`;
    try {
      const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
      const payload = await response.json();
      if (!response.ok || payload.error) throw Object.assign(new Error(payload.error || `HTTP ${response.status}`), { payload });
      renderPlayer(payload);
    } catch (error) {
      renderError(error instanceof Error ? error.message : "unknown error", error && error.payload && error.payload.legacy_href);
    }
  }

  loadPlayerPage();
})();
