const { request } = require("../../utils/api");
const { take } = require("../../utils/format");

Page({
  data: {
    loading: true,
    error: "",
    hero: {},
    metrics: [],
    guilds: []
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
      const payload = await request("/api/guilds");
      this.setData({
        loading: false,
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

  openGuildDetail(event) {
    const guildId = event.currentTarget.dataset.guildId;
    if (!guildId) {
      return;
    }
    wx.navigateTo({ url: `/pages/guild-detail/guild-detail?guild_id=${encodeURIComponent(guildId)}` });
  }
});
