(function () {
  const bootstrap = window.__WEREWOLF_COMPETITIONS_BOOTSTRAP__ || {};
  const root = document.getElementById("competitions-app");

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

  function renderAlert() {
    if (!bootstrap.alert) {
      return "";
    }
    return `<div class="competitions-alert">${escapeHtml(bootstrap.alert)}</div>`;
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
      return '<div class="competitions-chip-empty">先选择赛事后再切换赛季。</div>';
    }
    return `
      <select class="competitions-select" data-season-switcher>
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

  function renderActions(actions) {
    const links = [];
    if (actions.create_match_href) {
      links.push(
        `<a class="competitions-button competitions-button-primary" href="${escapeHtml(
          actions.create_match_href
        )}">创建或导入比赛</a>`
      );
    }
    if (actions.edit_competition_href) {
      links.push(
        `<a class="competitions-button competitions-button-secondary" href="${escapeHtml(
          actions.edit_competition_href
        )}">编辑赛事页信息</a>`
      );
    }
    if (actions.series_topic_href) {
      links.push(
        `<a class="competitions-button competitions-button-secondary" href="${escapeHtml(
          actions.series_topic_href
        )}">查看系列专题页</a>`
      );
    }
    if (actions.season_manage_href) {
      links.push(
        `<a class="competitions-button competitions-button-secondary" href="${escapeHtml(
          actions.season_manage_href
        )}">管理赛季档期</a>`
      );
    }
    if (actions.schedule_href) {
      links.push(
        `<a class="competitions-button competitions-button-secondary" href="${escapeHtml(
          actions.schedule_href
        )}">查看全部场次</a>`
      );
    }
    links.push(
      `<a class="competitions-button competitions-button-secondary" href="${escapeHtml(
        actions.back_href
      )}">返回地区赛事列表</a>`
    );
    return `<div class="competitions-hero-actions">${links.join("")}</div>`;
  }

  function renderListView(payload) {
    const hero = payload.hero || {};
    const scope = payload.scope || {};
    root.innerHTML = `
      <div class="competitions-layout">
        ${renderAlert()}
        <section class="competitions-hero">
          <article class="competitions-panel competitions-hero-main">
            <div class="competitions-section-kicker">Regional Event Portals</div>
            <h1 class="competitions-title">${escapeHtml(hero.title || "比赛页面")}</h1>
            <p class="competitions-copy">${escapeHtml(hero.copy || "")}</p>
            <div class="competitions-filter-grid">
              <section class="competitions-filter-card">
                <div class="competitions-filter-label">赛区切换</div>
                ${renderChipLinks(scope.filters && scope.filters.regions)}
              </section>
              <section class="competitions-filter-card">
                <div class="competitions-filter-label">系列赛切换</div>
                ${renderChipLinks(scope.filters && scope.filters.series)}
              </section>
            </div>
            <div class="competitions-hero-actions">
              ${
                payload.management && payload.management.can_manage_series
                  ? `<a class="competitions-button competitions-button-primary" href="${escapeHtml(
                      payload.management.manage_href
                    )}">创建或维护系列赛</a>`
                  : ""
              }
              <a class="competitions-button competitions-button-secondary" href="${escapeHtml(
                payload.legacy_href || "/competitions/legacy"
              )}">查看旧版赛事页</a>
            </div>
          </article>
          <aside class="competitions-panel competitions-hero-side">
            <div class="competitions-panel-kicker">Featured Event</div>
            <h2 class="competitions-section-title">${escapeHtml(hero.featured_name || "等待录入赛事")}</h2>
            <p class="competitions-copy">先从地区赛事站点选一个入口，再继续下钻到该赛事的赛季详情。</p>
            <div class="competitions-sidebar-grid">
              <div class="competitions-side-metric">
                <div class="competitions-stat-label">最近比赛日</div>
                <strong>${escapeHtml(hero.featured_latest || "待更新")}</strong>
                <div class="competitions-meta-text">${escapeHtml(hero.featured_seasons || "赛季待录入")}</div>
              </div>
            </div>
          </aside>
        </section>
        ${renderMetrics(payload.metrics || [])}
        <section class="competitions-panel competitions-section">
          <div class="competitions-section-head">
            <div>
              <div class="competitions-section-kicker">Regional Sites</div>
              <h2 class="competitions-section-title">该地区系列赛站点</h2>
              <p class="competitions-copy">同一系列赛可以进入专题页查看跨地区汇总，也可以单独进入当前地区赛事页查看该站独立赛季。</p>
            </div>
          </div>
          ${
            (payload.cards || []).length
              ? `
                <div class="competitions-card-grid">
                  ${payload.cards
                    .map(
                      (card) => `
                        <article class="competitions-card">
                          <div>
                            <div class="competitions-card-kicker">${escapeHtml(card.region_name)} · ${escapeHtml(
                        card.series_name
                      )}</div>
                            <h3 class="competitions-card-title">${escapeHtml(card.competition_name)}</h3>
                            <div class="competitions-meta-text">赛季 ${(card.seasons || [])
                              .map((season) => escapeHtml(season))
                              .join("、") || "待录入"}</div>
                            <div class="competitions-meta-text">最近比赛日 ${escapeHtml(card.latest_played_on)}</div>
                            <p class="competitions-card-copy">${escapeHtml(card.summary)}</p>
                          </div>
                          <div class="competitions-card-stat-grid">
                            <div class="competitions-card-stat"><span>战队</span><strong>${escapeHtml(
                              card.team_count
                            )} 支</strong></div>
                            <div class="competitions-card-stat"><span>队员</span><strong>${escapeHtml(
                              card.player_count
                            )} 名</strong></div>
                            <div class="competitions-card-stat"><span>对局</span><strong>${escapeHtml(
                              card.match_count
                            )} 场</strong></div>
                          </div>
                          <div class="competitions-card-actions">
                            <a class="competitions-button competitions-button-primary" href="${escapeHtml(
                              card.topic_href
                            )}">查看系列专题</a>
                            <a class="competitions-button competitions-button-secondary" href="${escapeHtml(
                              card.competition_href
                            )}">进入地区赛事页</a>
                          </div>
                        </article>
                      `
                    )
                    .join("")}
                </div>
              `
              : `
                <div class="competitions-empty-state">
                  <div class="competitions-panel-kicker">Empty</div>
                  <h3>当前地区还没有系列赛站点</h3>
                  <p class="competitions-empty-copy">可以先维护系列赛目录，或者继续录入已有赛事数据。</p>
                </div>
              `
          }
        </section>
      </div>
    `;
  }

  function renderTeamTable(rows) {
    if (!rows.length) {
      return '<div class="competitions-chip-empty">当前没有可展示的战队积分数据。</div>';
    }
    return `
      <div class="competitions-table-panel">
        <table class="competitions-table">
          <thead>
            <tr><th>排名</th><th>战队</th><th>场次</th><th>队员</th><th>总积分</th><th>场均</th><th>胜率</th></tr>
          </thead>
          <tbody>
            ${rows
              .map(
                (row) => `
                  <tr>
                    <td>${escapeHtml(row.rank)}</td>
                    <td><a href="${escapeHtml(row.href)}">${escapeHtml(row.name)}</a></td>
                    <td>${escapeHtml(row.matches_represented)}</td>
                    <td>${escapeHtml(row.player_count)}</td>
                    <td>${escapeHtml(row.points_total)}</td>
                    <td>${escapeHtml(row.points_per_match)}</td>
                    <td>${escapeHtml(row.win_rate)}</td>
                  </tr>
                `
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderPlayerTable(rows) {
    if (!rows.length) {
      return '<div class="competitions-chip-empty">当前没有个人积分数据。</div>';
    }
    return `
      <div class="competitions-table-panel">
        <table class="competitions-table">
          <thead>
            <tr><th>排名</th><th>选手</th><th>战队</th><th>出场</th><th>战绩</th><th>总积分</th><th>场均</th><th>胜率</th></tr>
          </thead>
          <tbody>
            ${rows
              .map(
                (row) => `
                  <tr>
                    <td>${escapeHtml(row.rank)}</td>
                    <td><a href="${escapeHtml(row.href)}">${escapeHtml(row.display_name)}</a></td>
                    <td>${escapeHtml(row.team_name)}</td>
                    <td>${escapeHtml(row.games_played)}</td>
                    <td>${escapeHtml(row.record)}</td>
                    <td>${escapeHtml(row.points_total)}</td>
                    <td>${escapeHtml(row.average_points)}</td>
                    <td>${escapeHtml(row.win_rate)}</td>
                  </tr>
                `
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderMvpTable(rows) {
    if (!rows.length) {
      return '<div class="competitions-chip-empty">当前还没有 MVP 数据。</div>';
    }
    return `
      <div class="competitions-table-panel">
        <table class="competitions-table">
          <thead>
            <tr><th>排名</th><th>选手</th><th>战队</th><th>MVP 次数</th><th>最近获奖</th></tr>
          </thead>
          <tbody>
            ${rows
              .map(
                (row) => `
                  <tr>
                    <td>${escapeHtml(row.rank)}</td>
                    <td><a href="${escapeHtml(row.href)}">${escapeHtml(row.display_name)}</a></td>
                    <td>${escapeHtml(row.team_name)}</td>
                    <td>${escapeHtml(row.mvp_count)}</td>
                    <td>${escapeHtml(row.latest_awarded_on)}</td>
                  </tr>
                `
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderGroupBoards(items) {
    if (!items.length) {
      return '<div class="competitions-chip-empty">当前赛季还没有可统计的分组战队积分数据。</div>';
    }
    return `
      <div class="competitions-group-grid">
        ${items
          .map(
            (stage) => `
              <section class="competitions-group-card">
                <div class="competitions-panel-kicker">${escapeHtml(stage.stage_label)}</div>
                ${stage.groups
                  .map(
                    (group) => `
                      <div class="competitions-section-head">
                        <div>
                          <h3 class="competitions-section-title">${escapeHtml(group.group_label)}</h3>
                        </div>
                      </div>
                      ${renderTeamTable(group.rows || [])}
                    `
                  )
                  .join("")}
              </section>
            `
          )
          .join("")}
      </div>
    `;
  }

  function renderAiPanel(ai) {
    const summary = ai.summary;
    const generateForm = ai.generate_form;
    const editForm = ai.edit_form;
    return `
      <section class="competitions-panel competitions-section">
        <div class="competitions-section-head">
          <div>
            <div class="competitions-section-kicker">AI Summary</div>
            <h2 class="competitions-section-title">AI 赛季总结</h2>
            <p class="competitions-copy">基于当前赛事页下该赛季的已录入数据生成总结，可在补录后重新生成。</p>
          </div>
          <div class="competitions-hero-actions">
            ${
              generateForm
                ? `
                  <form class="competitions-inline-form" method="post" action="/competitions">
                    ${Object.entries(generateForm.fields)
                      .map(
                        ([key, value]) =>
                          `<input type="hidden" name="${escapeHtml(key)}" value="${escapeHtml(value)}">`
                      )
                      .join("")}
                    <button class="competitions-button competitions-button-primary" type="submit">${escapeHtml(
                      generateForm.button_label
                    )}</button>
                  </form>
                `
                : !ai.configured
                ? `<a class="competitions-button competitions-button-secondary" href="${escapeHtml(
                    ai.settings_href
                  )}">前往账号管理配置 AI 接口</a>`
                : ""
            }
          </div>
        </div>
        ${
          summary
            ? `
              <div class="competitions-ai-summary">
                <div class="competitions-meta-text">生成时间 ${escapeHtml(summary.generated_at)} · 模型 ${escapeHtml(
                summary.model
              )}</div>
                <div class="competitions-editorial">${summary.html}</div>
              </div>
            `
            : `
              <div class="competitions-season-card">
                <div class="competitions-note">${
                  ai.configured ? "当前赛季还没有生成 AI 总结。" : "当前还没有配置 AI 接口。"
                }</div>
              </div>
            `
        }
        ${
          editForm
            ? `
              <section class="competitions-form-panel competitions-panel">
                <div class="competitions-section-head">
                  <div>
                    <div class="competitions-section-kicker">Admin Edit</div>
                    <h3 class="competitions-section-title">管理员编辑总结</h3>
                    <p class="competitions-copy">保存后会立即覆盖展示内容。</p>
                  </div>
                </div>
                <form method="post" action="/competitions">
                  ${Object.entries(editForm.fields)
                    .map(
                      ([key, value]) =>
                        `<input type="hidden" name="${escapeHtml(key)}" value="${escapeHtml(value)}">`
                    )
                    .join("")}
                  <textarea class="competitions-textarea" name="summary_content">${escapeHtml(
                    editForm.content
                  )}</textarea>
                  <div class="competitions-hero-actions" style="margin-top: 14px;">
                    <button class="competitions-button competitions-button-secondary" type="submit">保存人工编辑</button>
                  </div>
                </form>
              </section>
            `
            : ""
        }
      </section>
    `;
  }

  function renderSeasonInfoPanel(seasonInfo) {
    if (!seasonInfo.name) {
      return "";
    }
    return `
      <section class="competitions-panel competitions-section">
        <div class="competitions-section-head">
          <div>
            <div class="competitions-section-kicker">Season Window</div>
            <h2 class="competitions-section-title">赛季档期</h2>
            <p class="competitions-copy">当前查看的是 ${escapeHtml(
              seasonInfo.name
            )}。赛季战队与队员由比赛补录、战队档案和管理员维护直接决定。</p>
          </div>
        </div>
        <div class="competitions-season-card">
          <div class="competitions-panel-kicker">赛季状态</div>
          <h3 class="competitions-section-title">${escapeHtml(seasonInfo.status || "待配置")}</h3>
          <div class="competitions-meta-text">起止时间 ${escapeHtml(seasonInfo.period || "待补充")}</div>
          <p class="competitions-copy">${escapeHtml(seasonInfo.note || "")}</p>
        </div>
      </section>
    `;
  }

  function renderDetailView(payload) {
    const scope = payload.scope || {};
    const hero = payload.hero || {};
    const actions = payload.actions || {};
    const seasonInfo = payload.season_info || {};
    const leaderboards = payload.leaderboards || {};
    root.innerHTML = `
      <div class="competitions-layout">
        ${renderAlert()}
        <section class="competitions-hero">
          <article class="competitions-panel competitions-hero-main">
            <div class="competitions-section-kicker">${escapeHtml(hero.badge || "Event Sheet")}</div>
            <h1 class="competitions-title">${escapeHtml(hero.title || scope.label || "比赛页面")}</h1>
            <p class="competitions-copy">${escapeHtml(hero.intro || "")}</p>
            <div class="competitions-filter-grid">
              <section class="competitions-filter-card">
                <div class="competitions-filter-label">赛区切换</div>
                ${renderChipLinks(scope.filters && scope.filters.regions)}
              </section>
              <section class="competitions-filter-card">
                <div class="competitions-filter-label">系列赛切换</div>
                ${renderChipLinks(scope.filters && scope.filters.series)}
              </section>
              <section class="competitions-filter-card">
                <div class="competitions-filter-label">赛事切换</div>
                ${renderChipLinks(scope.filters && scope.filters.competitions)}
              </section>
              <section class="competitions-filter-card">
                <div class="competitions-filter-label">赛季切换</div>
                ${renderSeasonSelect(scope.filters && scope.filters.seasons)}
              </section>
            </div>
            ${renderActions(actions)}
          </article>
          <aside class="competitions-panel competitions-hero-side">
            <div class="competitions-panel-kicker">Season Overview</div>
            <h2 class="competitions-section-title">${escapeHtml(scope.label || "赛季总览")}</h2>
            <p class="competitions-copy">${escapeHtml(hero.note || "")}</p>
            <div class="competitions-sidebar-grid">
              <div class="competitions-side-metric">
                <div class="competitions-stat-label">最近比赛日</div>
                <strong>${escapeHtml(hero.latest_played_on || "待更新")}</strong>
                <div class="competitions-meta-text">${escapeHtml(hero.latest_seasons || "赛季待录入")}</div>
              </div>
              <div class="competitions-side-metric">
                <div class="competitions-stat-label">旧版页面</div>
                <a class="competitions-button competitions-button-secondary" href="${escapeHtml(
                  payload.legacy_href || "/competitions/legacy"
                )}">查看旧版赛事页</a>
              </div>
            </div>
          </aside>
        </section>
        ${renderMetrics(payload.metrics || [])}
        <section class="competitions-panel competitions-section">
          <div class="competitions-section-head">
            <div>
              <div class="competitions-section-kicker">Leaderboards</div>
              <h2 class="competitions-section-title">积分榜</h2>
              <p class="competitions-copy">页面先直接展示战队积分榜，你可以继续切换到分组战队榜、个人积分榜或 MVP 榜。</p>
            </div>
          </div>
          <div class="competitions-board-tabs">
            <button class="competitions-tab is-active" data-board-tab="team" type="button">战队积分榜</button>
            <button class="competitions-tab" data-board-tab="group-team" type="button">分组战队榜</button>
            <button class="competitions-tab" data-board-tab="player" type="button">个人积分榜</button>
            <button class="competitions-tab" data-board-tab="mvp" type="button">个人 MVP 榜</button>
          </div>
          <div class="competitions-board-panel" data-board-panel="team">
            <div class="competitions-board-grid">
              ${(leaderboards.stage_team || [])
                .map(
                  (stage) => `
                    <section class="competitions-group-card">
                      <div class="competitions-panel-kicker">${escapeHtml(stage.stage_label)}</div>
                      ${renderTeamTable(stage.rows || [])}
                    </section>
                  `
                )
                .join("") || '<div class="competitions-chip-empty">当前赛季还没有可统计的赛段战队积分数据。</div>'}
            </div>
          </div>
          <div class="competitions-board-panel" data-board-panel="group-team" hidden>
            ${renderGroupBoards(leaderboards.group_team || [])}
          </div>
          <div class="competitions-board-panel" data-board-panel="player" hidden>
            ${renderPlayerTable(leaderboards.players || [])}
          </div>
          <div class="competitions-board-panel" data-board-panel="mvp" hidden>
            ${renderMvpTable(leaderboards.mvp || [])}
          </div>
        </section>
        <section class="competitions-summary-stack">
          ${renderSeasonInfoPanel(seasonInfo)}
          ${renderAiPanel(payload.ai || {})}
        </section>
        <section class="competitions-main-grid">
          <section class="competitions-panel competitions-section">
            <div class="competitions-section-head">
              <div>
                <div class="competitions-section-kicker">Team Links</div>
                <h2 class="competitions-section-title">该赛季战队入口</h2>
                <p class="competitions-copy">这里只保留当前赛季的战队名称入口，点进后继续看同一赛季口径下的战队详情。</p>
              </div>
            </div>
            <div class="competitions-team-links">
              ${(payload.teams || [])
                .map(
                  (team) => `
                    <a class="competitions-chip" href="${escapeHtml(team.href)}">${escapeHtml(team.name)}</a>
                  `
                )
                .join("") || '<div class="competitions-chip-empty">当前赛季还没有战队数据。</div>'}
            </div>
          </section>
          <aside class="competitions-panel competitions-sidebar">
            <div class="competitions-section-head">
              <div>
                <div class="competitions-section-kicker">Season Days</div>
                <h2 class="competitions-section-title">比赛日入口</h2>
                <p class="competitions-copy">当前先用比赛日卡片做下钻入口，方便继续拆成更完整的前端赛程视图。</p>
              </div>
            </div>
            <div class="competitions-day-grid">
              ${(payload.match_days || [])
                .map(
                  (day) => `
                    <a class="competitions-day-card" href="${escapeHtml(day.href)}">
                      <div class="competitions-panel-kicker">Match Day</div>
                      <div class="competitions-section-title">${escapeHtml(day.played_on)}</div>
                      <div class="competitions-day-count">${escapeHtml(day.match_count)} 场</div>
                    </a>
                  `
                )
                .join("") || '<div class="competitions-chip-empty">当前赛季还没有比赛日数据。</div>'}
            </div>
          </aside>
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

    const tabs = Array.from(root.querySelectorAll("[data-board-tab]"));
    const panels = Array.from(root.querySelectorAll("[data-board-panel]"));
    tabs.forEach((tab) => {
      tab.addEventListener("click", function () {
        const selected = tab.getAttribute("data-board-tab");
        tabs.forEach((item) =>
          item.classList.toggle("is-active", item.getAttribute("data-board-tab") === selected)
        );
        panels.forEach((panel) => {
          panel.hidden = panel.getAttribute("data-board-panel") !== selected;
        });
      });
    });
  }

  function renderError(message) {
    root.innerHTML = `
      <section class="competitions-error-shell">
        <div class="competitions-loading-kicker">Load Failed</div>
        <h1>比赛页面加载失败</h1>
        <p>${escapeHtml(message)}</p>
        <p><a href="/competitions/legacy">可以先打开旧版比赛页面继续使用</a></p>
      </section>
    `;
  }

  async function loadCompetitions() {
    const endpoint = `${bootstrap.apiEndpoint || "/api/competitions"}${window.location.search || ""}`;
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
      if (payload.view === "detail") {
        renderDetailView(payload);
      } else {
        renderListView(payload);
      }
    } catch (error) {
      renderError(error instanceof Error ? error.message : "unknown error");
    }
  }

  loadCompetitions();
})();
