(function () {
  const bootstrap = window.__WEREWOLF_MATCH_BOOTSTRAP__ || {};
  const root = document.getElementById("match-app");

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

  function renderMetrics(metrics) {
    return `
      <section class="competitions-metrics-grid match-detail-metrics-grid">
        ${(metrics || []).map((item) => `
          <article class="competitions-metric match-detail-metric">
            <div class="competitions-stat-label">${escapeHtml(item.label)}</div>
            <div class="competitions-stat-value">${escapeHtml(item.value)}</div>
            <p class="competitions-card-copy">${escapeHtml(item.copy || "")}</p>
          </article>
        `).join("")}
      </section>
    `;
  }

  function renderAwards(awards) {
    return `
      <div class="match-detail-award-grid">
        ${(awards || []).map((award) => `
          <article class="match-detail-card">
            <div class="competitions-section-kicker">${escapeHtml(award.label)}</div>
            ${award.player_id ? `
              <a class="match-detail-card-title" href="${escapeHtml(award.href)}">${escapeHtml(award.player_name)}</a>
              <p>${escapeHtml(award.meta || "")}</p>
            ` : `<p>${escapeHtml(award.empty_label || "暂未设置")}</p>`}
          </article>
        `).join("")}
      </div>
    `;
  }

  function renderScores(scores) {
    return `
      <div class="match-detail-score-grid">
        ${(scores || []).map((item) => `
          <a class="match-detail-card" href="${escapeHtml(item.href || "#")}">
            <div class="competitions-section-kicker">战队积分</div>
            <div class="match-detail-score-value">${escapeHtml(item.points)}</div>
            <p>${escapeHtml(item.team_name)}</p>
          </a>
        `).join("")}
      </div>
    `;
  }

  function renderParticipants(participants, scoreFields) {
    const fields = Array.isArray(scoreFields) ? scoreFields : [];
    const items = Array.isArray(participants) ? participants : [];
    if (!items.length) return `<div class="competitions-empty-state">暂无上场成员记录。</div>`;
    return `
      <div class="match-detail-table-wrap">
        <table class="match-detail-table">
          <thead>
            <tr>
              <th>座位</th><th>队员</th><th>战队</th><th>角色</th><th>阵营</th><th>结果</th>
              ${fields.map((field) => `<th>${escapeHtml(field)}</th>`).join("")}
              <th>站边</th><th>得分</th><th>备注</th>
            </tr>
          </thead>
          <tbody>
            ${items.map((item) => `
              <tr>
                <td>${escapeHtml(item.seat)}</td>
                <td><a href="${escapeHtml(item.player_href || "#")}">${escapeHtml(item.player_name)}</a></td>
                <td><a href="${escapeHtml(item.team_href || "#")}">${escapeHtml(item.team_name)}</a></td>
                <td>${escapeHtml(item.role)}</td>
                <td>${escapeHtml(item.camp)}</td>
                <td>${escapeHtml(item.result)}</td>
                ${fields.map((field) => `<td>${escapeHtml((item.breakdown || {})[field] || 0)}</td>`).join("")}
                <td>${escapeHtml(item.stance)}</td>
                <td>${escapeHtml(item.points)}</td>
                <td>${escapeHtml(item.notes || "无")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderMatch(payload) {
    const match = payload.match || {};
    const actions = payload.actions || {};
    if (payload.title) document.title = payload.title;
    root.innerHTML = `
      ${renderAlert(payload.alert || bootstrap.alert)}
      <section class="match-detail-hero">
        <article class="competitions-panel match-detail-hero-main">
          <div class="competitions-section-kicker">Match Detail</div>
          <h1 class="competitions-title">${escapeHtml(match.competition || "比赛详情")}</h1>
          <p class="competitions-copy">${escapeHtml(match.season || "")}</p>
          <div class="match-detail-meta-row">
            <span>编号 ${escapeHtml(match.match_id)}</span>
            <span>${escapeHtml(match.stage)}</span>
            <span>第 ${escapeHtml(match.round)} 轮 第 ${escapeHtml(match.game_no)} 局</span>
            <span>${escapeHtml(match.played_on)}</span>
            <span>计分模型 ${escapeHtml(match.score_model)}</span>
          </div>
          <div class="competitions-hero-actions match-detail-actions">
            <a class="competitions-button competitions-button-secondary" href="${escapeHtml(actions.next_href || "/competitions")}">返回上一页</a>
            <a class="competitions-button competitions-button-secondary" href="${escapeHtml(match.day_href || "/schedule")}">查看比赛日</a>
            ${actions.edit_href ? `<a class="competitions-button competitions-button-primary" href="${escapeHtml(actions.edit_href)}">编辑比赛</a>` : ""}
            <a class="competitions-button competitions-button-secondary" href="${escapeHtml(actions.legacy_href || bootstrap.legacyHref || "#")}">查看旧版</a>
          </div>
        </article>
        ${renderMetrics(payload.metrics)}
      </section>
      <section class="competitions-panel match-detail-section">
        <div class="competitions-section-head"><div><div class="competitions-section-kicker">Awards</div><h2 class="competitions-section-title">本局奖项</h2><p class="competitions-copy">记录每场比赛的 MVP、SVP 和背锅选手。</p></div></div>
        ${renderAwards(payload.awards)}
      </section>
      <section class="competitions-panel match-detail-section">
        <div class="competitions-section-head"><div><div class="competitions-section-kicker">Team Scores</div><h2 class="competitions-section-title">战队比分</h2><p class="competitions-copy">按本场所有上场成员的得分累计展示。</p></div></div>
        ${renderScores(payload.team_scores)}
      </section>
      <section class="competitions-panel match-detail-section">
        <div class="competitions-section-head"><div><div class="competitions-section-kicker">Participants</div><h2 class="competitions-section-title">上场成员明细</h2><p class="competitions-copy">点击队员或战队名称，可以继续跳转到对应详情页。</p></div></div>
        ${renderParticipants(payload.participants, payload.score_fields)}
      </section>
      <section class="competitions-panel match-detail-section">
        <div class="competitions-section-kicker">Notes</div>
        <h2 class="competitions-section-title">比赛备注</h2>
        <p class="competitions-copy">${escapeHtml(match.notes || "暂无备注。")}</p>
      </section>
    `;
  }

  function renderError(message, legacyHref) {
    root.innerHTML = `
      <section class="competitions-panel competitions-empty-state">
        <div class="competitions-section-kicker">Load Failed</div>
        <h1 class="competitions-title">比赛详情加载失败</h1>
        <p class="competitions-copy">${escapeHtml(message || "unknown error")}</p>
        <a class="competitions-button competitions-button-secondary" href="${escapeHtml(legacyHref || bootstrap.legacyHref || "/competitions")}">打开旧版比赛页</a>
      </section>
    `;
  }

  async function loadMatchPage() {
    const endpoint = `${bootstrap.apiEndpoint || ""}${window.location.search || ""}`;
    try {
      const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
      const payload = await response.json();
      if (!response.ok || payload.error) throw Object.assign(new Error(payload.error || `HTTP ${response.status}`), { payload });
      renderMatch(payload);
    } catch (error) {
      renderError(error instanceof Error ? error.message : "unknown error", error && error.payload && error.payload.legacy_href);
    }
  }

  loadMatchPage();
})();
