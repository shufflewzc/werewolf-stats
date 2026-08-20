const STORAGE_KEY = "werewolf:selectedCompetition";

function text(value) {
  return String(value === undefined || value === null ? "" : value).trim();
}

function normalizeScope(scope = {}) {
  const normalized = {
    competition: text(scope.competition),
    season: text(scope.season),
    region: text(scope.region),
    series: text(scope.series),
    seriesName: text(scope.seriesName || scope.series_name),
    latestPlayedOn: text(scope.latestPlayedOn),
    teamCount: Number(scope.teamCount || 0),
    playerCount: Number(scope.playerCount || 0),
    matchCount: Number(scope.matchCount || 0)
  };
  normalized.displayMeta = [normalized.region, normalized.seriesName, normalized.season]
    .filter(Boolean)
    .join(" · ");
  return normalized;
}

function isCompleteScope(scope) {
  const normalized = normalizeScope(scope);
  return Boolean(normalized.competition && normalized.season);
}

function sameScope(left, right) {
  const normalizedLeft = normalizeScope(left);
  const normalizedRight = normalizeScope(right);
  return Boolean(
    normalizedLeft.competition
    && normalizedLeft.season
    && normalizedLeft.competition === normalizedRight.competition
    && normalizedLeft.season === normalizedRight.season
  );
}

function parseQueryFromHref(href) {
  const query = String(href || "").split("?")[1] || "";
  return query.split("&").reduce((result, item) => {
    const [rawKey, rawValue] = item.split("=");
    if (!rawKey) {
      return result;
    }
    result[decodeURIComponent(rawKey)] = decodeURIComponent(rawValue || "");
    return result;
  }, {});
}

function buildScopeFromCompetition(card, selectedSeason) {
  const query = parseQueryFromHref(card && card.competition_href);
  const seasons = Array.isArray(card && card.seasons) ? card.seasons : [];
  const season = text(selectedSeason || (card && card.selectedSeason));
  const competition = text((card && card.competition_name) || query.competition);
  if (!competition || !season || !seasons.includes(season)) {
    return null;
  }
  return normalizeScope({
    competition,
    season,
    region: (card && card.region_name) || query.region || "",
    series: query.series || "",
    seriesName: (card && card.series_name) || "",
    latestPlayedOn: (card && card.latest_played_on) || "",
    teamCount: Number((card && card.team_count) || 0),
    playerCount: Number((card && card.player_count) || 0),
    matchCount: Number((card && card.match_count) || 0)
  });
}

function getSelectedScope() {
  const stored = wx.getStorageSync(STORAGE_KEY) || null;
  if (!stored) {
    return null;
  }
  if (!isCompleteScope(stored)) {
    wx.removeStorageSync(STORAGE_KEY);
    return null;
  }
  return normalizeScope(stored);
}

function getRequiredScope() {
  return getSelectedScope();
}

function setSelectedScope(scope) {
  if (!isCompleteScope(scope)) {
    return null;
  }
  const normalized = normalizeScope(scope);
  wx.setStorageSync(STORAGE_KEY, normalized);
  return normalized;
}

function decodeOption(value) {
  try {
    return decodeURIComponent(value || "");
  } catch (error) {
    return String(value || "");
  }
}

function scopeOptionsState(options = {}) {
  const hasCompetition = Object.prototype.hasOwnProperty.call(options, "competition");
  const hasSeason = Object.prototype.hasOwnProperty.call(options, "season");
  if (!hasCompetition && !hasSeason) {
    return { status: "none", scope: null };
  }
  const scope = normalizeScope({
    competition: decodeOption(options.competition),
    season: decodeOption(options.season),
    region: decodeOption(options.region),
    series: decodeOption(options.series),
    seriesName: decodeOption(options.series_name)
  });
  if (!hasCompetition || !hasSeason || !isCompleteScope(scope)) {
    return { status: "invalid", scope: null };
  }
  return { status: "complete", scope };
}

function scopeFromOptions(options = {}) {
  const state = scopeOptionsState(options);
  return state.status === "complete" ? state.scope : null;
}

async function resolveScopeFromCatalog(scope) {
  const target = normalizeScope(scope);
  if (!isCompleteScope(target)) {
    return null;
  }
  const { request } = require("./api");
  const payload = await request(
    "/api/competitions",
    { grouped: "1" },
    { useCache: false }
  );
  const groupedCards = (payload.city_groups || []).reduce(
    (result, group) => result.concat(Array.isArray(group && group.cards) ? group.cards : []),
    []
  );
  const cards = groupedCards.length ? groupedCards : (payload.cards || []);
  const card = cards.find((item) => (
    item
    && text(item.competition_name) === target.competition
    && Array.isArray(item.seasons)
    && item.seasons.map(text).includes(target.season)
  ));
  return card ? buildScopeFromCompetition(card, target.season) : null;
}

function confirmScopeSwitch(scope, options = {}) {
  const target = normalizeScope(scope);
  if (!isCompleteScope(target)) {
    return Promise.resolve({ accepted: false, status: "invalid", scope: getRequiredScope() });
  }
  const current = getRequiredScope();
  if (sameScope(current, target)) {
    return Promise.resolve({ accepted: true, status: "same", scope: current });
  }
  const sourceLabel = text(options.sourceLabel) || "该内容";
  const currentCopy = current
    ? `当前选择是「${current.competition} · ${current.season}」。`
    : "当前尚未选择赛事和赛季。";
  return new Promise((resolve) => {
    wx.showModal({
      title: options.title || "切换赛事和赛季",
      content: `${sourceLabel}属于「${target.competition} · ${target.season}」。${currentCopy}是否切换后继续？`,
      confirmText: "确认切换",
      cancelText: "取消",
      async success(result) {
        if (!result.confirm) {
          resolve({ accepted: false, status: "cancelled", scope: current });
          return;
        }
        try {
          const catalogScope = await resolveScopeFromCatalog(target);
          const selected = catalogScope ? setSelectedScope(catalogScope) : null;
          resolve({
            accepted: Boolean(selected),
            status: selected ? "switched" : "not_found",
            scope: selected || current
          });
        } catch (error) {
          resolve({
            accepted: false,
            status: "catalog_error",
            scope: current,
            error
          });
        }
      },
      fail() {
        resolve({ accepted: false, status: "cancelled", scope: current });
      }
    });
  });
}

function applyScopeFromOptions(options = {}, config = {}) {
  const state = scopeOptionsState(options);
  if (state.status === "none") {
    return Promise.resolve({ accepted: true, status: "none", scope: getRequiredScope() });
  }
  if (state.status === "invalid") {
    return Promise.resolve({ accepted: false, status: "invalid", scope: getRequiredScope() });
  }
  return confirmScopeSwitch(state.scope, config);
}

function confirmScopeMismatch(error, config = {}) {
  if (!error || error.code !== "SCOPE_MISMATCH") {
    return Promise.resolve(null);
  }
  const payload = error.payload && typeof error.payload === "object" ? error.payload : {};
  const resourceScope = payload.resource_scope || payload.scope || null;
  if (!isCompleteScope(resourceScope)) {
    return Promise.resolve({ accepted: false, status: "invalid", scope: getRequiredScope() });
  }
  return confirmScopeSwitch(resourceScope, {
    title: config.title || "内容属于其他赛季",
    sourceLabel: config.sourceLabel || "该内容"
  });
}

function scopeActivationError(result) {
  if (result && result.status === "cancelled") {
    return "已取消切换，当前赛事和赛季未改变。";
  }
  if (result && result.status === "not_found") {
    return "目标赛事或赛季已失效，请从赛事入口重新选择。";
  }
  if (result && result.status === "catalog_error") {
    return "暂时无法验证目标赛事和赛季，请稍后重试。";
  }
  return "链接缺少完整的赛事和赛季，请从赛事入口重新进入。";
}

function appendScopeToPath(path, scope = getRequiredScope()) {
  if (!isCompleteScope(scope)) {
    return path;
  }
  const normalized = normalizeScope(scope);
  const separator = String(path).indexOf("?") >= 0 ? "&" : "?";
  const query = {
    ...scopeParams(normalized),
    series_name: normalized.seriesName
  };
  delete query.scope_required;
  const encoded = Object.keys(query)
    .filter((key) => query[key])
    .map((key) => `${encodeURIComponent(key)}=${encodeURIComponent(query[key])}`)
    .join("&");
  return encoded ? `${path}${separator}${encoded}` : path;
}

function clearSelectedScope() {
  wx.removeStorageSync(STORAGE_KEY);
}

function scopeParams(scope) {
  if (!isCompleteScope(scope)) {
    return { scope_required: "1" };
  }
  const normalized = normalizeScope(scope);
  return {
    competition: normalized.competition,
    season: normalized.season,
    region: normalized.region,
    series: normalized.series,
    scope_required: "1"
  };
}

function optionalScopeParams(scope) {
  if (!isCompleteScope(scope)) {
    return {};
  }
  // 全局展示接口可接收当前选择用于文案，但其响应不承诺 scoped payload。
  const params = { ...scopeParams(scope) };
  delete params.scope_required;
  return params;
}

function needsCompetitionState(extra = {}) {
  return Object.assign({
    loading: false,
    error: "",
    selectedScope: null,
    needsCompetition: true
  }, extra);
}

function goCompetitions() {
  wx.switchTab({ url: "/pages/competitions/competitions" });
}

module.exports = {
  buildScopeFromCompetition,
  appendScopeToPath,
  applyScopeFromOptions,
  clearSelectedScope,
  confirmScopeMismatch,
  confirmScopeSwitch,
  getRequiredScope,
  getSelectedScope,
  goCompetitions,
  isCompleteScope,
  needsCompetitionState,
  normalizeScope,
  optionalScopeParams,
  resolveScopeFromCatalog,
  sameScope,
  scopeActivationError,
  scopeFromOptions,
  scopeParams,
  setSelectedScope
};
