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
  const isSelectedSeason = Boolean(isSelectedCompetition && selectedScope.season === selectedSeason);
  return {
    ...card,
    seasons,
    selectedSeason,
    selectedSeasonIndex,
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
    const isSelectedSeason = Boolean(
      this.data.selectedScope
      && this.data.selectedScope.competition === card.competition_name
      && this.data.selectedScope.season === selectedSeason
    );
    this.setData({
      [`cards[${index}].selectedSeasonIndex`]: seasonIndex,
      [`cards[${index}].selectedSeason`]: selectedSeason,
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
