const { request } = require("../../utils/api");
const { getSelectedScope, scopeParams } = require("../../utils/scope");

function decoratePrediction(item) {
  const system = item.probabilities || [];
  const manual = item.manual_probabilities || [];
  const manualFilled = manual.some((entry) => entry.value !== null && entry.value !== undefined);
  return {
    ...item,
    primaryProbability: system[3] || system[0] || {},
    system,
    manual,
    manualFilled
  };
}

Page({
  data: {
    loading: true,
    error: "",
    needsCompetition: false,
    selectedScope: null,
    scope: {},
    matches: [],
    selectedMatch: null,
    predictions: [],
    buckets: [],
    notice: ""
  },

  onLoad(options) {
    this.initialMatchId = options.match_id || "";
  },

  onShow() {
    this.loadData(this.initialMatchId);
    this.initialMatchId = "";
  },

  onPullDownRefresh() {
    const matchId = this.data.selectedMatch && this.data.selectedMatch.match_id;
    this.loadData(matchId || "").finally(() => wx.stopPullDownRefresh());
  },

  async loadData(matchId = "") {
    this.setData({ loading: true, error: "" });
    try {
      const selectedScope = getSelectedScope();
      if (!selectedScope || !selectedScope.competition) {
        this.setData({
          loading: false,
          needsCompetition: true,
          selectedScope: null,
          scope: {},
          matches: [],
          selectedMatch: null,
          predictions: [],
          buckets: [],
          notice: ""
        });
        return;
      }
      const params = {
        ...scopeParams(selectedScope),
        match_id: matchId
      };
      const payload = await request("/api/predictions", params);
      this.setData({
        loading: false,
        needsCompetition: false,
        selectedScope,
        scope: payload.scope || {},
        matches: payload.matches || [],
        selectedMatch: payload.selected_match || null,
        predictions: (payload.predictions || []).map(decoratePrediction),
        buckets: payload.prediction_buckets || [],
        notice: payload.notice || ""
      });
    } catch (error) {
      this.setData({
        loading: false,
        error: error.message || "胜率预测加载失败"
      });
    }
  },

  chooseMatch(event) {
    const matchId = event.currentTarget.dataset.matchId;
    if (!matchId || (this.data.selectedMatch && this.data.selectedMatch.match_id === matchId)) {
      return;
    }
    this.loadData(matchId);
  },

  openPlayer(event) {
    const playerId = event.currentTarget.dataset.playerId;
    if (!playerId) {
      return;
    }
    wx.navigateTo({ url: `/pages/player-detail/player-detail?player_id=${encodeURIComponent(playerId)}` });
  },

  goCompetitions() {
    wx.switchTab({ url: "/pages/dashboard/dashboard" });
  }
});
