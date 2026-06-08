const { bindPlayer, getCurrentUser, searchPlayers } = require("../../utils/auth");

Page({
  data: {
    loading: false,
    error: "",
    keyword: "",
    players: [],
    user: null
  },

  onShow() {
    this.setData({ user: getCurrentUser() });
  },

  updateKeyword(event) {
    this.setData({ keyword: event.detail.value });
  },

  async search() {
    const keyword = this.data.keyword.trim();
    if (!keyword) {
      this.setData({ error: "请输入中文名字。", players: [] });
      return;
    }
    this.setData({ loading: true, error: "" });
    try {
      const payload = await searchPlayers(keyword);
      this.setData({ loading: false, players: payload.players || [] });
    } catch (error) {
      this.setData({ loading: false, error: error.message || "搜索失败" });
    }
  },

  async bind(event) {
    const playerId = event.currentTarget.dataset.playerId;
    if (!playerId) {
      return;
    }
    this.setData({ loading: true, error: "" });
    try {
      await bindPlayer(playerId);
      this.setData({ loading: false });
      wx.showToast({ title: "绑定成功", icon: "success" });
      setTimeout(() => wx.navigateBack(), 500);
    } catch (error) {
      this.setData({ loading: false, error: error.message || "绑定失败" });
    }
  }
});
