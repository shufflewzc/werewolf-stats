const { request } = require("../../utils/api");
const { setSelectedScope } = require("../../utils/scope");

Page({
  onLoad(options) {
    const scene = decodeURIComponent(options.scene || "");
    this.openSharedPlayer(scene);
  },

  async openSharedPlayer(scene) {
    try {
      const payload = await request("/api/miniprogram/share-entry", { scene }, { useCache: false });
      if (!payload.scope || !payload.scope.competition) {
        throw new Error("分享内容暂时无法打开。");
      }
      setSelectedScope(payload.scope);
      if (payload.target === "prediction_day" && payload.played_on) {
        wx.redirectTo({
          url: `/pages/predictions/predictions?played_on=${encodeURIComponent(payload.played_on)}`
        });
        return;
      }
      if (!payload.player_id) {
        throw new Error("分享内容暂时无法打开。");
      }
      wx.redirectTo({
        url: `/pages/player-detail/player-detail?player_id=${encodeURIComponent(payload.player_id)}`
      });
    } catch (error) {
      wx.showModal({
        title: "无法打开分享内容",
        content: error.message || "分享内容已失效，请稍后重试。",
        showCancel: false,
        complete() {
          wx.switchTab({ url: "/pages/dashboard/dashboard" });
        }
      });
    }
  }
});
