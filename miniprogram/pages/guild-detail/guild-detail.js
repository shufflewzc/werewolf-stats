const { request } = require("../../utils/api");
const { take } = require("../../utils/format");

Page({
  data: {
    loading: true,
    error: "",
    guildId: "",
    guild: {},
    metrics: [],
    ongoingTeams: [],
    historySections: [],
    honors: []
  },

  onLoad(options) {
    this.setData({ guildId: decodeURIComponent(options.guild_id || "") });
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData().finally(() => wx.stopPullDownRefresh());
  },

  async loadData() {
    const guildId = this.data.guildId;
    if (!guildId) {
      this.setData({ loading: false, error: "缺少门派 ID" });
      return;
    }

    this.setData({ loading: true, error: "" });
    try {
      const payload = await request(`/api/guilds/${encodeURIComponent(guildId)}`);
      const guild = payload.guild || {};
      wx.setNavigationBarTitle({ title: guild.name || "门派详情" });
      this.setData({
        loading: false,
        guild,
        metrics: take(payload.metrics, 4),
        ongoingTeams: payload.ongoing_teams || [],
        historySections: payload.history_sections || [],
        honors: payload.honors || []
      });
    } catch (error) {
      this.setData({
        loading: false,
        error: error.message || "门派详情加载失败"
      });
    }
  }
});
