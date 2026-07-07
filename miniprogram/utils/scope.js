const STORAGE_KEY = "werewolf:selectedCompetition";

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
  const season = selectedSeason || (card && card.selectedSeason) || seasons[0] || query.season || "";
  return {
    competition: (card && card.competition_name) || query.competition || "",
    season,
    region: (card && card.region_name) || query.region || "",
    series: query.series || "",
    seriesName: (card && card.series_name) || "",
    latestPlayedOn: (card && card.latest_played_on) || "",
    teamCount: Number((card && card.team_count) || 0),
    playerCount: Number((card && card.player_count) || 0),
    matchCount: Number((card && card.match_count) || 0)
  };
}

function getSelectedScope() {
  return wx.getStorageSync(STORAGE_KEY) || null;
}

function getRequiredScope() {
  const scope = getSelectedScope();
  return scope && scope.competition ? scope : null;
}

function setSelectedScope(scope) {
  wx.setStorageSync(STORAGE_KEY, scope || null);
}

function clearSelectedScope() {
  wx.removeStorageSync(STORAGE_KEY);
}

function scopeParams(scope) {
  if (!scope || !scope.competition) {
    return {};
  }
  return {
    competition: scope.competition,
    season: scope.season,
    region: scope.region,
    series: scope.series
  };
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
  clearSelectedScope,
  getRequiredScope,
  getSelectedScope,
  goCompetitions,
  needsCompetitionState,
  scopeParams,
  setSelectedScope
};
