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

  function renderSummaryItem(label, record, value, kind) {
    if (!record) {
      return `
        <div class="dashboard-brief-item">
          <span class="dashboard-rank-badge">${escapeHtml(label)}</span>
          <div>
            <div class="dashboard-brief-name">等待录入</div>
            <div class="dashboard-ranking-meta">当前口径下暂无有效战绩。</div>
          </div>
          <div class="dashboard-brief-value">--<small>${escapeHtml(kind)}</small></div>
        </div>
      `;
    }
    const meta =
      kind === "team"
        ? `胜率 ${escapeHtml(record.win_rate)} · 对局 ${escapeHtml(record.matches_represented)} 场`
        : `胜率 ${escapeHtml(record.win_rate)} · 出场 ${escapeHtml(record.games_played)} 次`;
    return `
      <a class="dashboard-brief-item" href="${escapeHtml(record.href)}">
        <span class="dashboard-rank-badge">${escapeHtml(label)}</span>
        <div>
          <div class="dashboard-brief-name">${escapeHtml(
            record.name || record.display_name
          )}</div>
          <div class="dashboard-ranking-meta">${meta}</div>
        </div>
        <div class="dashboard-brief-value">${escapeHtml(value)}<small>${escapeHtml(kind)}</small></div>
      </a>
    `;
  }

  function renderMetrics(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return "";
    }
    return `
      <section class="dashboard-metrics-grid">
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
                  <p class="dashboard-card-copy">
                    ${escapeHtml(item.summary || "先看专题，再进入具体地区赛事页。")}
                  </p>
                </div>
                <div class="dashboard-card-stat-grid">
                  <div class="dashboard-card-stat">
                    <span>战队</span>
                    <strong>${escapeHtml(item.team_count)} 支</strong>
                  </div>
                  <div class="dashboard-card-stat">
                    <span>队员</span>
                    <strong>${escapeHtml(item.player_count)} 名</strong>
                  </div>
                  <div class="dashboard-card-stat">
                    <span>对局</span>
                    <strong>${escapeHtml(item.match_count)} 场</strong>
                  </div>
                </div>
                <div class="dashboard-card-copy">
                  赛季 ${escapeHtml((item.seasons || []).join("、") || "未设置")} · 下一个比赛日 ${escapeHtml(
                    item.latest_played_on
                  )}
                </div>
                <div class="dashboard-card-actions">
                  <a class="dashboard-card-link dashboard-card-link-primary" href="${escapeHtml(
                    item.topic_href
                  )}">查看系列专题</a>
                  <a class="dashboard-card-link dashboard-card-link-secondary" href="${escapeHtml(
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

  function renderRankingItems(items, kind) {
    if (!Array.isArray(items) || items.length === 0) {
      return '<div class="dashboard-select-note">当前没有可展示的榜单。</div>';
    }
    return `
      <div class="dashboard-ranking-list">
        ${items
          .map((item) => {
            const name = kind === "team" ? item.name : item.display_name;
            const meta =
              kind === "team"
                ? `${item.win_rate} 胜率 · ${item.matches_represented} 场`
                : `${item.team_name} · ${item.games_played} 场`;
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
                <div class="dashboard-ranking-value">${escapeHtml(item.points_total)}<small>${escapeHtml(
                  kind
                )}</small></div>
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
      <div class="dashboard-days-grid">
        ${items
          .map(
            (item) => `
              <a class="dashboard-day-card" href="${escapeHtml(item.href)}">
                <div class="dashboard-card-kicker">Match Day</div>
                <div class="dashboard-day-title">${escapeHtml(item.played_on)}</div>
                <div class="dashboard-day-meta">共 ${escapeHtml(item.match_count)} 场比赛</div>
                <div class="dashboard-day-count">${escapeHtml(item.match_count)} 场</div>
                <div class="dashboard-day-tags">
                  ${(item.competition_names || [])
                    .map(
                      (name) => `<span class="dashboard-day-tag">${escapeHtml(name)}</span>`
                    )
                    .join("")}
                </div>
              </a>
            `
          )
          .join("")}
      </div>
    `;
  }

  function renderDashboard(payload) {
    const scope = payload.scope || {};
    const hero = payload.hero || {};
    root.innerHTML = `
      <div class="dashboard-layout">
        ${renderAlert(bootstrap.alert)}
        <section class="dashboard-hero">
          <article class="dashboard-panel dashboard-hero-main">
            <div class="dashboard-section-kicker">Frontend + API</div>
            <h1 class="dashboard-hero-title">${escapeHtml(
              scope.dashboard_label || hero.featured_label || "赛事首页"
            )}</h1>
            <p class="dashboard-hero-copy">${escapeHtml(scope.description || "")}</p>
            <div class="dashboard-filter-grid">
              <section class="dashboard-filter-card">
                <div class="dashboard-filter-label">赛区切换</div>
                ${renderChipLinks(scope.filters && scope.filters.regions)}
              </section>
              <section class="dashboard-filter-card">
                <div class="dashboard-filter-label">系列赛切换</div>
                ${renderChipLinks(scope.filters && scope.filters.series)}
              </section>
              <section class="dashboard-filter-card">
                <div class="dashboard-filter-label">赛事切换</div>
                ${renderChipLinks(scope.filters && scope.filters.competitions)}
              </section>
              <section class="dashboard-filter-card">
                <div class="dashboard-filter-label">赛季切换</div>
                ${renderSeasonSelect(scope.filters && scope.filters.seasons)}
              </section>
            </div>
            <div class="dashboard-hero-actions">
              <a class="dashboard-card-link dashboard-card-link-primary" href="${escapeHtml(
                hero.latest_match_day_href || hero.competitions_href || "/competitions"
              )}">打开比赛日时间线</a>
              <a class="dashboard-card-link dashboard-card-link-secondary" href="${escapeHtml(
                hero.competitions_href || "/competitions"
              )}">打开全部赛事</a>
              <a class="dashboard-card-link dashboard-card-link-secondary" href="${escapeHtml(
                payload.legacy_href || "/dashboard/legacy"
              )}">查看旧版首页</a>
            </div>
          </article>
          <aside class="dashboard-hero-side">
            <section class="dashboard-panel dashboard-spotlight">
              <div class="dashboard-panel-kicker">Featured Scope</div>
              <div class="dashboard-spotlight-title">${escapeHtml(
                hero.featured_label || "等待录入赛事"
              )}</div>
              <p class="dashboard-spotlight-copy">
                当前仪表盘优先展示这个范围下最值得继续查看的内容。先看榜单，再进入系列赛或某个比赛日。
              </p>
              <div class="dashboard-spotlight-grid">
                <div class="dashboard-spotlight-metric">
                  <span>赛季范围</span>
                  <strong>${escapeHtml(hero.featured_seasons || "赛季待录入")}</strong>
                  <small>${escapeHtml(scope.label || "")}</small>
                </div>
                <div class="dashboard-spotlight-metric">
                  <span>最近比赛日</span>
                  <strong>${escapeHtml(hero.latest_played_on || "待录入")}</strong>
                  <small>${escapeHtml(payload.generated_at || "")}</small>
                </div>
                <div class="dashboard-spotlight-metric">
                  <span>头名战队</span>
                  <strong>${escapeHtml(
                    (hero.top_team && hero.top_team.name) || "等待录入"
                  )}</strong>
                  <small>${escapeHtml(
                    hero.top_team ? `${hero.top_team.points_total} 分` : "暂无战绩"
                  )}</small>
                </div>
                <div class="dashboard-spotlight-metric">
                  <span>头名选手</span>
                  <strong>${escapeHtml(
                    (hero.top_player && hero.top_player.display_name) || "等待录入"
                  )}</strong>
                  <small>${escapeHtml(
                    hero.top_player ? `${hero.top_player.points_total} 分` : "暂无战绩"
                  )}</small>
                </div>
              </div>
            </section>
            <section class="dashboard-panel dashboard-brief">
              <div class="dashboard-panel-kicker">Quick Brief</div>
              <div class="dashboard-brief-list">
                ${renderSummaryItem(
                  "T",
                  hero.top_team,
                  hero.top_team ? hero.top_team.points_total : "--",
                  "team"
                )}
                ${renderSummaryItem(
                  "P",
                  hero.top_player,
                  hero.top_player ? hero.top_player.points_total : "--",
                  "player"
                )}
              </div>
            </section>
          </aside>
        </section>
        ${renderMetrics(payload.metrics)}
        <section class="dashboard-main-grid">
          <section class="dashboard-panel dashboard-section">
            <div class="dashboard-section-head">
              <div>
                <div class="dashboard-section-kicker">Series Topics</div>
                <h2 class="dashboard-section-title">系列赛专题入口</h2>
                <p class="dashboard-section-copy">首页先摆出值得点进去的专题，再往下进入地区赛事页。</p>
              </div>
              <a class="dashboard-section-action" href="/competitions">进入全部赛事</a>
            </div>
            ${renderSeriesCards(payload.series_cards)}
          </section>
          <aside class="dashboard-panel dashboard-ranking-panel">
            <div class="dashboard-ranking-block">
              <div class="dashboard-panel-kicker">Top Teams</div>
              <h2 class="dashboard-section-title">即时战队榜</h2>
              ${renderRankingItems(payload.top_teams, "team")}
            </div>
            <div class="dashboard-ranking-block">
              <div class="dashboard-panel-kicker">Top Players</div>
              <h2 class="dashboard-section-title">即时选手榜</h2>
              ${renderRankingItems(payload.top_players, "player")}
            </div>
          </aside>
        </section>
        <section class="dashboard-panel dashboard-section">
          <div class="dashboard-section-head">
            <div>
              <div class="dashboard-section-kicker">Recent Days</div>
              <h2 class="dashboard-section-title">最近比赛日</h2>
              <p class="dashboard-section-copy">从“今天发生了什么”这个入口快速下钻到比赛日时间线。</p>
            </div>
            <a class="dashboard-inline-link" href="${escapeHtml(
              hero.latest_match_day_href || "/competitions"
            )}">查看最新时间线</a>
          </div>
          ${renderDays(payload.match_days)}
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
      const response = await fetch(endpoint, {
        headers: {
          Accept: "application/json",
        },
      });
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
