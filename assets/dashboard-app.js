(function () {
  const bootstrap = window.__WEREWOLF_DASHBOARD_BOOTSTRAP__ || {};
  const root = document.getElementById("dashboard-app");

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
    return `<div class="dashboard-alert">${escapeHtml(message)}</div>`;
  }

  function firstItems(items, count) {
    return Array.isArray(items) ? items.slice(0, count) : [];
  }

  function getMetricValue(metrics, label, fallback) {
    const item = Array.isArray(metrics) ? metrics.find((metric) => metric.label === label) : null;
    return item ? item.value : fallback;
  }

  function renderChipLinks(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return '<div class="dashboard-select-note">当前没有可切换的选项。</div>';
    }
    return `
      <div class="dashboard-chip-list">
        ${items
          .map(
            (item) => `
              <a class="dashboard-chip${item.active ? " is-active" : ""}" href="${escapeHtml(item.href)}">
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
      return '<div class="dashboard-select-note">先选择赛事后再切换赛季。</div>';
    }
    return `
      <select class="dashboard-select" data-season-switcher>
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

  function renderHeroStats(payload) {
    const hero = payload.hero || {};
    const metrics = payload.metrics || [];
    return `
      <div class="dashboard-hero-stat-row">
        <div class="dashboard-hero-stat is-matches">
          <span class="dashboard-hero-stat-icon"></span>
          <strong>${escapeHtml(getMetricValue(metrics, "比赛场次", "--"))}</strong>
          <small>比赛场次<br>MATCHES</small>
        </div>
        <div class="dashboard-hero-stat is-teams">
          <span class="dashboard-hero-stat-icon"></span>
          <strong>${escapeHtml(getMetricValue(metrics, "收录战队", "--"))}</strong>
          <small>参赛战队<br>TEAMS</small>
        </div>
        <div class="dashboard-hero-stat is-players">
          <span class="dashboard-hero-stat-icon"></span>
          <strong>${escapeHtml(getMetricValue(metrics, "出场队员", "--"))}</strong>
          <small>出场选手<br>PLAYERS</small>
        </div>
        <div class="dashboard-hero-stat is-status">
          <span class="dashboard-hero-stat-icon"></span>
          <strong>进行中</strong>
          <small>${escapeHtml(hero.latest_played_on || "待录入")}<br>STATUS</small>
        </div>
      </div>
    `;
  }

  function renderSchedule(payload) {
    const hero = payload.hero || {};
    const stageLabels = {
      regular_season: "常规赛",
      placement: "定位赛",
      group_stage: "小组赛",
      knockout: "淘汰赛",
      semifinal: "半决赛",
      final: "决赛",
    };
    const scheduleItems = Array.isArray(payload.schedule_matches) ? payload.schedule_matches : [];
    const rows = (scheduleItems.length ? scheduleItems : [0, 1, 2]).slice(0, 3).map((item, index) => {
      const match = typeof item === "object" ? item : null;
      const stage = match ? stageLabels[match.stage] || match.stage || "赛段待定" : "赛段待定";
      const game = match ? `第${match.round || "-"}轮第${match.game_no || "-"}局` : `第${index + 1}轮第-局`;
      return `
        <a class="dashboard-schedule-row" href="${escapeHtml((match && match.href) || hero.latest_match_day_href || "/competitions")}">
          <span class="dashboard-schedule-dot"></span>
          <div class="dashboard-schedule-name">${escapeHtml(stage)}</div>
          <div class="dashboard-schedule-time"><strong>${escapeHtml(game)}</strong><span>${escapeHtml((match && match.table_label) || "")}</span></div>
        </a>
      `;
    });
    return `
      <aside class="dashboard-panel dashboard-schedule-card">
        <div class="dashboard-schedule-head">
          <div>
            <div class="dashboard-panel-kicker">今日赛程</div>
            <strong>${escapeHtml(hero.latest_played_on || "待录入")}</strong>
          </div>
          <span>星期五</span>
        </div>
        <div class="dashboard-schedule-list">${rows.join("")}</div>
        <a class="dashboard-section-action" href="${escapeHtml(hero.latest_match_day_href || "/competitions")}">查看完整赛程</a>
      </aside>
    `;
  }

  function renderMetrics(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return "";
    }
    return `
      <section class="dashboard-panel dashboard-overview-panel">
        <div class="dashboard-section-head">
          <div>
            <div class="dashboard-section-kicker">数据概览</div>
            <h2 class="dashboard-section-title">赛区数据概览</h2>
          </div>
        </div>
        <div class="dashboard-metrics-grid">
          ${items
            .map(
              (item) => `
                <article class="dashboard-metric-card">
                  <span class="dashboard-metric-label">${escapeHtml(item.label)}</span>
                  <strong class="dashboard-metric-value">${escapeHtml(item.value)}</strong>
                  <small class="dashboard-metric-copy">${escapeHtml(item.copy)}</small>
                </article>
              `
            )
            .join("")}
        </div>
      </section>
    `;
  }

  function renderSeriesCards(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return `
        <div class="dashboard-empty-state">
          <div class="dashboard-card-kicker">Series Empty</div>
          <h3>当前地区还没有系列赛</h3>
          <p>可以先去后台维护系列赛目录，或者继续从比赛页录入已有赛事数据。</p>
        </div>
      `;
    }
    return `
      <div class="dashboard-series-grid">
        ${items
          .map(
            (item) => `
              <article class="dashboard-series-card">
                <div>
                  <div class="dashboard-card-kicker">${escapeHtml(item.region_name)} · Series Topic</div>
                  <h3 class="dashboard-card-title">${escapeHtml(item.series_name)}</h3>
                  <p class="dashboard-card-copy">${escapeHtml(item.summary || "先看专题，再进入具体地区赛事页。")}</p>
                </div>
                <div class="dashboard-card-stat-grid">
                  <div class="dashboard-card-stat"><span>战队</span><strong>${escapeHtml(item.team_count)} 支</strong></div>
                  <div class="dashboard-card-stat"><span>队员</span><strong>${escapeHtml(item.player_count)} 名</strong></div>
                  <div class="dashboard-card-stat"><span>对局</span><strong>${escapeHtml(item.match_count)} 场</strong></div>
                </div>
                <div class="dashboard-card-copy">赛季 ${escapeHtml((item.seasons || []).join("、") || "未设置")} · 下一个比赛日 ${escapeHtml(item.latest_played_on)}</div>
                <div class="dashboard-card-actions">
                  <a class="dashboard-card-link dashboard-card-link-primary" href="${escapeHtml(item.topic_href)}">查看系列专题</a>
                  <a class="dashboard-card-link dashboard-card-link-secondary" href="${escapeHtml(item.competition_href)}">进入地区赛事页</a>
                </div>
              </article>
            `
          )
          .join("")}
      </div>
    `;
  }

  function renderRankingItems(items, kind) {
    if (!Array.isArray(items) || items.length === 0) {
      return '<div class="dashboard-select-note">当前口径下暂无榜单数据。</div>';
    }
    return `
      <div class="dashboard-ranking-list">
        ${items
          .slice(0, 5)
          .map((item) => {
            const name = kind === "team" ? item.name : item.display_name;
            const meta = kind === "team" ? `${item.win_rate} 胜率 · ${item.matches_represented} 场` : `${item.team_name} · ${item.games_played} 场`;
            const avatar = kind === "team" ? item.logo : item.photo;
            return `
              <a class="dashboard-ranking-item" href="${escapeHtml(item.href)}">
                <span class="dashboard-ranking-rank">${escapeHtml(item.rank)}</span>
                <div class="dashboard-ranking-main">
                  <img class="dashboard-ranking-avatar" src="${escapeHtml(avatar)}" alt="${escapeHtml(name)}">
                  <div class="dashboard-ranking-copy">
                    <div class="dashboard-ranking-name">${escapeHtml(name)}</div>
                    <div class="dashboard-ranking-meta">${escapeHtml(meta)}</div>
                  </div>
                </div>
                <div class="dashboard-ranking-value">${escapeHtml(item.points_total)}<small>分</small></div>
              </a>
            `;
          })
          .join("")}
      </div>
    `;
  }

  function renderDays(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return `
        <div class="dashboard-empty-state">
          <div class="dashboard-card-kicker">Days Empty</div>
          <h3>当前范围还没有比赛日数据</h3>
          <p>比赛录入完成后，这里会自动出现可下钻的时间线入口。</p>
        </div>
      `;
    }
    return `
      <div class="dashboard-days-list">
        ${items
          .slice(0, 3)
          .map(
            (item, index) => `
              <a class="dashboard-day-card${index === 0 ? " is-current" : ""}" href="${escapeHtml(item.href)}">
                <div class="dashboard-day-date"><strong>${escapeHtml(item.played_on.slice(5).replace("-", "/"))}</strong><span>${index === 0 ? "今日" : "赛程"}</span></div>
                <div class="dashboard-day-main">
                  <div class="dashboard-day-title">${escapeHtml((item.competition_names || [])[0] || "比赛日")}</div>
                  <div class="dashboard-day-meta">比赛场次：${escapeHtml(item.match_count)} 场</div>
                  <div class="dashboard-day-tags">
                    ${(item.competition_names || [])
                      .slice(0, 6)
                      .map((name) => `<span class="dashboard-day-tag">${escapeHtml(name)}</span>`)
                      .join("")}
                  </div>
                </div>
                <span class="dashboard-card-arrow">›</span>
              </a>
            `
          )
          .join("")}
      </div>
    `;
  }

  function renderActivity(payload) {
    const items = Array.isArray(payload.activity_feed) ? payload.activity_feed : [];
    if (items.length === 0) {
      return `
        <section class="dashboard-panel dashboard-section dashboard-activity-panel">
          <div class="dashboard-section-head">
            <div><div class="dashboard-section-kicker">Event Feed</div><h2 class="dashboard-section-title">赛事动态</h2></div>
            <a class="dashboard-section-action" href="/competitions">更多</a>
          </div>
          <div class="dashboard-select-note">当前范围还没有可生成特殊事件的有效比赛记录。</div>
        </section>
      `;
    }
    return `
      <section class="dashboard-panel dashboard-section dashboard-activity-panel">
        <div class="dashboard-section-head">
          <div><div class="dashboard-section-kicker">Event Feed</div><h2 class="dashboard-section-title">赛事动态</h2></div>
          <a class="dashboard-section-action" href="/competitions">更多</a>
        </div>
        <div class="dashboard-activity-list">
          ${items
            .map(
              (item) => `
                <a class="dashboard-activity-item" href="${escapeHtml(item.href || "/competitions")}">
                  <time>${escapeHtml(item.time_label)}</time>
                  <span></span>
                  <p>${escapeHtml(item.text)}</p>
                  <strong>${escapeHtml(item.label)}</strong>
                </a>
              `
            )
            .join("")}
        </div>
      </section>
    `;
  }

  function renderHighlights(payload) {
    const topPlayer = payload.hero && payload.hero.top_player;
    const topTeam = payload.hero && payload.hero.top_team;
    return `
      <section class="dashboard-panel dashboard-section dashboard-highlight-panel">
        <div class="dashboard-section-head">
          <div><div class="dashboard-section-kicker">Highlights</div><h2 class="dashboard-section-title">精彩瞬间</h2></div>
          <a class="dashboard-section-action" href="/competitions">更多</a>
        </div>
        <a class="dashboard-feature-video" href="${escapeHtml((payload.hero && payload.hero.latest_match_day_href) || "/competitions")}">
          <span class="dashboard-video-badge">TOP1</span>
          <span class="dashboard-play-button"></span>
          <div><strong>${escapeHtml((topPlayer && topPlayer.display_name) || "极限反杀四人")}</strong><small>${escapeHtml((topTeam && topTeam.name) || "赛事精彩回放")} · ${escapeHtml((payload.hero && payload.hero.latest_played_on) || "待录入")}</small></div>
        </a>
        <div class="dashboard-video-strip">
          ${[0, 1, 2, 3].map(() => '<span><i></i></span>').join("")}
        </div>
      </section>
    `;
  }

  function renderHeroFilters(scope) {
    return `
      <div class="dashboard-filter-grid">
        <section class="dashboard-filter-card"><div class="dashboard-filter-label">赛区切换</div>${renderChipLinks(scope.filters && scope.filters.regions)}</section>
        <section class="dashboard-filter-card"><div class="dashboard-filter-label">系列赛切换</div>${renderChipLinks(scope.filters && scope.filters.series)}</section>
        <section class="dashboard-filter-card"><div class="dashboard-filter-label">赛事切换</div>${renderChipLinks(scope.filters && scope.filters.competitions)}</section>
        <section class="dashboard-filter-card"><div class="dashboard-filter-label">赛季切换</div>${renderSeasonSelect(scope.filters && scope.filters.seasons)}</section>
      </div>
    `;
  }

  function renderDashboard(payload) {
    const scope = payload.scope || {};
    const hero = payload.hero || {};
    root.innerHTML = `
      <div class="dashboard-layout dashboard-reference-layout">
        ${renderAlert(bootstrap.alert)}
        <section class="dashboard-top-grid">
          <article class="dashboard-panel dashboard-hero-main dashboard-reference-hero">
            <div class="dashboard-section-kicker">${escapeHtml(scope.selected_region || "广州赛区")}</div>
            <h1 class="dashboard-hero-title">${escapeHtml(scope.dashboard_label || hero.featured_label || "赛事首页")}</h1>
            <p class="dashboard-hero-copy">群雄逐鹿 · 巅峰对决</p>
            ${renderHeroStats(payload)}
            ${renderHeroFilters(scope)}
            <div class="dashboard-hero-actions">
              <a class="dashboard-card-link dashboard-card-link-primary" href="${escapeHtml(hero.latest_match_day_href || hero.competitions_href || "/competitions")}">打开比赛日时间线</a>
              <a class="dashboard-card-link dashboard-card-link-secondary" href="${escapeHtml(hero.competitions_href || "/competitions")}">打开全部赛事</a>
            </div>
          </article>
          ${renderSchedule(payload)}
        </section>

        ${renderMetrics(payload.metrics)}

        <section class="dashboard-board-grid">
          <section class="dashboard-panel dashboard-section dashboard-ranking-panel">
            <div class="dashboard-section-head">
              <div><div class="dashboard-section-kicker">Team Ranking</div><h2 class="dashboard-section-title">战队排行榜</h2></div>
              <a class="dashboard-section-action" href="/competitions">更多</a>
            </div>
            ${renderRankingItems(payload.top_teams, "team")}
          </section>
          <section class="dashboard-panel dashboard-section dashboard-ranking-panel">
            <div class="dashboard-section-head">
              <div><div class="dashboard-section-kicker">Player Ranking</div><h2 class="dashboard-section-title">选手排行榜</h2></div>
              <a class="dashboard-section-action" href="/competitions">更多</a>
            </div>
            ${renderRankingItems(payload.top_players, "player")}
          </section>
        </section>

        <section class="dashboard-lower-grid">
          <section class="dashboard-panel dashboard-section dashboard-days-panel">
            <div class="dashboard-section-head">
              <div><div class="dashboard-section-kicker">Recent Match Days</div><h2 class="dashboard-section-title">最近比赛日</h2></div>
              <a class="dashboard-section-action" href="${escapeHtml(hero.latest_match_day_href || "/competitions")}">更多</a>
            </div>
            ${renderDays(payload.match_days)}
          </section>
          ${renderActivity(payload)}
          ${renderHighlights(payload)}
        </section>

        <section class="dashboard-panel dashboard-section dashboard-series-panel">
          <div class="dashboard-section-head">
            <div><div class="dashboard-section-kicker">Series Topics</div><h2 class="dashboard-section-title">赛事专题</h2></div>
            <a class="dashboard-section-action" href="/competitions">进入全部赛事</a>
          </div>
          ${renderSeriesCards(payload.series_cards)}
        </section>

        <section class="dashboard-glory-banner">
          <div><strong>为荣耀而战</strong><span>每一场比赛，都是传奇的开始</span></div>
          <a class="dashboard-card-link dashboard-card-link-secondary" href="/competitions">查看赛事专题</a>
        </section>
      </div>
    `;

    const seasonSwitcher = root.querySelector("[data-season-switcher]");
    if (seasonSwitcher) {
      seasonSwitcher.addEventListener("change", function (event) {
        const target = event.currentTarget;
        if (target && target.value) {
          window.location.href = target.value;
        }
      });
    }
  }

  function renderError(message) {
    root.innerHTML = `
      <section class="dashboard-error-shell">
        <div class="dashboard-loading-kicker">Load Failed</div>
        <h1>首页数据加载失败</h1>
        <p>${escapeHtml(message)}</p>
        <p><a class="dashboard-inline-link" href="/dashboard/legacy">可以先打开旧版首页继续使用</a></p>
      </section>
    `;
  }

  async function loadDashboard() {
    const endpoint = `${bootstrap.apiEndpoint || "/api/dashboard"}${window.location.search || ""}`;
    try {
      const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      renderDashboard(payload);
    } catch (error) {
      renderError(error instanceof Error ? error.message : "unknown error");
    }
  }

  loadDashboard();
})();
