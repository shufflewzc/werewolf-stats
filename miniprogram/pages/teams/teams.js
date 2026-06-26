const { request, assetUrl } = require("../../utils/api");
const { take } = require("../../utils/format");
const { getRequiredScope, goCompetitions, needsCompetitionState, scopeParams } = require("../../utils/scope");

Page({
  data: {
    loading: true,
    error: "",
    selectedScope: null,
    needsCompetition: false,
    scope: {},
    metrics: [],
    teams: []
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
      const selectedScope = getRequiredScope();
      if (!selectedScope) {
        this.setData(needsCompetitionState({
          scope: {},
          metrics: [],
          teams: []
        }));
        return;
      }

      const payload = await request("/api/teams", scopeParams(selectedScope));
      this.setData({
        loading: false,
        selectedScope,
        needsCompetition: false,
        scope: payload.scope || {},
        metrics: take(payload.metrics, 4),
        teams: (payload.teams || []).map((team) => ({
          ...team,
          logoUrl: assetUrl(team.logo)
        }))
      });
    } catch (error) {
      this.setData({
        loading: false,
        error: error.message || "门派数据加载失败"
      });
    }
  },

  goCompetitions() {
    goCompetitions();
  },

  onTeamImageError(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (!Number.isFinite(index)) {
      return;
    }
    this.setData({ [`teams[${index}].logoUrl`]: "" });
  }
});
