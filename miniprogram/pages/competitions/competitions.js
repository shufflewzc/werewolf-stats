const { request } = require("../../utils/api");
const { take } = require("../../utils/format");
const {
  buildScopeFromCompetition,
  getSelectedScope,
  setSelectedScope
} = require("../../utils/scope");

function decorateCompetitionCard(card, selectedScope) {
  const seasons = Array.isArray(card.seasons) ? card.seasons : [];
  const isSelectedCompetition = Boolean(selectedScope && selectedScope.competition === card.competition_name);
  const selectedSeasonIndex = isSelectedCompetition
    ? Math.max(0, seasons.indexOf(selectedScope.season))
    : 0;
  const selectedSeason = seasons[selectedSeasonIndex] || (isSelectedCompetition && selectedScope ? selectedScope.season : "") || "";
  const seasonStats = (card.season_stats && card.season_stats[selectedSeason]) || {};
  const isSelectedSeason = Boolean(isSelectedCompetition && selectedScope.season === selectedSeason);
  return {
    ...card,
    seasons,
    selectedSeason,
    selectedSeasonIndex,
    team_count: Number(seasonStats.team_count !== undefined ? seasonStats.team_count : card.team_count || 0),
    player_count: Number(seasonStats.player_count !== undefined ? seasonStats.player_count : card.player_count || 0),
    match_count: Number(seasonStats.match_count !== undefined ? seasonStats.match_count : card.match_count || 0),
    latest_played_on: seasonStats.latest_played_on || card.latest_played_on,
    hasMultipleSeasons: seasons.length > 1,
    isSelected: Boolean(isSelectedCompetition && isSelectedSeason),
    enterText: isSelectedCompetition && isSelectedSeason ? "重新进入当前赛季" : "进入该赛季"
  };
}

Page({
  data: {
    loading: true,
    error: "",
    selectedScope: null,
    view: "list",
    hero: {},
    metrics: [],
    cards: []
  },

  onShow() {
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData().finally(() => wx.stopPullDownRefresh());
  },

  async loadData() {
    this.setData({ loading: true, error: "" });
    try {
      const payload = await request("/api/competitions");
      const selectedScope = getSelectedScope();
      this.setData({
        loading: false,
        selectedScope,
        view: payload.view || "list",
        hero: payload.hero || {},
        metrics: take(payload.metrics, 4),
        cards: (payload.cards || []).map((card) => decorateCompetitionCard(card, selectedScope))
      });
    } catch (error) {
      this.setData({
        loading: false,
        error: error.message || "赛事数据加载失败"
      });
    }
  },

  chooseSeason(event) {
    const index = Number(event.currentTarget.dataset.index);
    const seasonIndex = Number(event.detail && event.detail.value);
    const card = this.data.cards[index];
    if (!card) {
      return;
    }
    const selectedSeason = card.seasons[seasonIndex] || "";
    const seasonStats = (card.season_stats && card.season_stats[selectedSeason]) || {};
    const isSelectedSeason = Boolean(
      this.data.selectedScope
      && this.data.selectedScope.competition === card.competition_name
      && this.data.selectedScope.season === selectedSeason
    );
    this.setData({
      [`cards[${index}].selectedSeasonIndex`]: seasonIndex,
      [`cards[${index}].selectedSeason`]: selectedSeason,
      [`cards[${index}].team_count`]: Number(seasonStats.team_count !== undefined ? seasonStats.team_count : card.team_count || 0),
      [`cards[${index}].player_count`]: Number(seasonStats.player_count !== undefined ? seasonStats.player_count : card.player_count || 0),
      [`cards[${index}].match_count`]: Number(seasonStats.match_count !== undefined ? seasonStats.match_count : card.match_count || 0),
      [`cards[${index}].latest_played_on`]: seasonStats.latest_played_on || card.latest_played_on,
      [`cards[${index}].isSelected`]: isSelectedSeason,
      [`cards[${index}].enterText`]: isSelectedSeason ? "重新进入当前赛季" : "进入该赛季"
    });
  },

  chooseCompetition(event) {
    const index = Number(event.currentTarget.dataset.index);
    const card = this.data.cards[index];
    if (!card) {
      return;
    }
    setSelectedScope(buildScopeFromCompetition(card, card.selectedSeason));
    wx.switchTab({ url: "/pages/dashboard/dashboard" });
  }
});
