const { request } = require("../../utils/api");
const { take } = require("../../utils/format");
const { getRequiredScope, goCompetitions, needsCompetitionState, scopeParams } = require("../../utils/scope");

Page({
  data: {
    loading: true,
    error: "",
    selectedScope: null,
    needsCompetition: false,
    hero: {},
    metrics: [],
    guilds: []
  },

  onShow() {
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData({ forceRefresh: true }).finally(() => wx.stopPullDownRefresh());
  },

  async loadData(options = {}) {
    this.setData({ loading: true, error: "" });
    try {
      const selectedScope = getRequiredScope();
      if (!selectedScope) {
        this.setData(needsCompetitionState({
          hero: {},
          metrics: [],
          guilds: []
        }));
        return;
      }

      const payload = await request("/api/guilds", scopeParams(selectedScope), options);
      this.setData({
        loading: false,
        selectedScope,
        needsCompetition: false,
        hero: payload.hero || {},
        metrics: take(payload.metrics, 4),
        guilds: payload.cards || []
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

  changeCompetition() {
    goCompetitions();
  },

  openGuildDetail(event) {
    const guildId = event.currentTarget.dataset.guildId;
    if (!guildId) {
      return;
    }
    wx.navigateTo({ url: `/pages/guild-detail/guild-detail?guild_id=${encodeURIComponent(guildId)}` });
  }
});
