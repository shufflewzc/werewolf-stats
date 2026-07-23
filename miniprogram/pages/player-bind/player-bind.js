const { bindPlayer, getCurrentUser, searchPlayers, unbindPlayer } = require("../../utils/auth");

function boundPlayersFromUser(user) {
  const explicitPlayers = Array.isArray(user && user.bound_players) ? user.bound_players : [];
  if (explicitPlayers.length) {
    return explicitPlayers;
  }
  const ids = Array.isArray(user && user.bound_player_ids) ? user.bound_player_ids : [];
  return ids.map((playerId) => ({
    player_id: playerId,
    display_name: playerId
  }));
}

Page({
  data: {
    loading: false,
    error: "",
    keyword: "",
    players: [],
    user: null,
    boundPlayers: []
  },

  onShow() {
    const user = getCurrentUser();
    this.setData({
      user,
      boundPlayers: boundPlayersFromUser(user)
    });
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
      const payload = await bindPlayer(playerId);
      const user = payload.user || getCurrentUser();
      const players = this.data.players.map((player) => ({
        ...player,
        bound_to_self: player.player_id === playerId,
        bound: player.bound || player.player_id === playerId
      }));
      this.setData({
        loading: false,
        user,
        boundPlayers: boundPlayersFromUser(user),
        players
      });
      wx.showToast({ title: "绑定成功", icon: "success" });
    } catch (error) {
      this.setData({ loading: false, error: error.message || "绑定失败" });
    }
  },

  unbind(event) {
    const playerId = event.currentTarget.dataset.playerId;
    const player = this.data.boundPlayers.find((item) => item.player_id === playerId);
    if (!playerId || !player) {
      return;
    }
    wx.showModal({
      title: "解除选手绑定",
      content: `确定解除“${player.display_name || playerId}”吗？如果该选手是战队负责人，负责人身份也会一并解除。`,
      confirmText: "解除绑定",
      confirmColor: "#b91c1c",
      success: async (result) => {
        if (!result.confirm) {
          return;
        }
        this.setData({ loading: true, error: "" });
        try {
          const payload = await unbindPlayer(playerId);
          const user = payload.user || getCurrentUser();
          this.setData({
            loading: false,
            user,
            boundPlayers: boundPlayersFromUser(user),
            players: this.data.players.map((item) => (
              item.player_id === playerId
                ? { ...item, bound: false, bound_to_self: false }
                : item
            ))
          });
          wx.showToast({ title: "已解除绑定", icon: "success" });
        } catch (error) {
          this.setData({ loading: false, error: error.message || "解绑失败" });
        }
      }
    });
  }
});
