const { request } = require("../../utils/api");
const { take } = require("../../utils/format");
const { appendScopeToPath, applyScopeFromOptions, getRequiredScope, goCompetitions, needsCompetitionState, optionalScopeParams, scopeActivationError } = require("../../utils/scope");

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

  onLoad(options) {
    this._scopeReady = applyScopeFromOptions(options, { sourceLabel: "分享的门派列表" });
  },

  async onShow() {
    if (this._scopeReady) {
      const activation = await this._scopeReady;
      this._scopeReady = null;
      if (!activation.accepted) {
        this._scopeEntryBlocked = scopeActivationError(activation);
        this.setData({ loading: false, error: this._scopeEntryBlocked });
        return false;
      }
    } else {
      this._scopeEntryBlocked = "";
    }
    return this.loadData();
  },

  onPullDownRefresh() {
    this.loadData({ forceRefresh: true }).finally(() => wx.stopPullDownRefresh());
  },

  onShareAppMessage() {
    const scope = this.data.selectedScope;
    return {
      title: `${scope && scope.competition ? scope.competition : "狼人杀赛事"} · ${scope && scope.season ? scope.season : "门派"}`,
      path: appendScopeToPath("/pages/guilds/guilds", scope)
    };
  },

  async loadData(options = {}) {
    if (this._scopeEntryBlocked) {
      this.setData({ loading: false, error: this._scopeEntryBlocked });
      return false;
    }
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

      const payload = await request("/api/guilds", optionalScopeParams(selectedScope), options);
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
