const { request, assetUrl } = require("../../utils/api");
const { take } = require("../../utils/format");
const { getSelectedScope, scopeParams } = require("../../utils/scope");

Page({
  data: {
    loading: true,
    error: "",
    playerId: "",
    player: {},
    metrics: [],
    insights: {},
    roles: [],
    recentMatches: [],
    dimension: {},
    dimensionAvailable: false
  },

  onLoad(options) {
    this.setData({ playerId: decodeURIComponent(options.player_id || "") });
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData().finally(() => wx.stopPullDownRefresh());
  },

  async loadData() {
    const playerId = this.data.playerId;
    if (!playerId) {
      this.setData({ loading: false, error: "缺少选手 ID" });
      return;
    }

    this.setData({ loading: true, error: "" });
    try {
      const selectedScope = getSelectedScope();
      const payload = await request(`/api/players/${encodeURIComponent(playerId)}`, scopeParams(selectedScope));
      const player = payload.player || {};
      const dimension = payload.dimension || {};
      const normalizedDimension = {
        ...dimension,
        radar: (dimension.radar || []).map((item) => ({
          ...item,
          width: Math.max(0, Math.min(100, Number(item.ratio || 0) * 100))
        }))
      };
      wx.setNavigationBarTitle({ title: player.name || "选手详情" });
      this.setData({
        loading: false,
        player: {
          ...player,
          photoUrl: assetUrl(player.photo)
        },
        metrics: take(payload.metrics, 6),
        insights: payload.insights || {},
        roles: take(payload.roles, 8),
        recentMatches: take(payload.recent_matches, 6),
        dimension: normalizedDimension,
        dimensionAvailable: Boolean(normalizedDimension.available)
      });
    } catch (error) {
      this.setData({
        loading: false,
        error: error.message || "选手详情加载失败"
      });
    }
  }
});
