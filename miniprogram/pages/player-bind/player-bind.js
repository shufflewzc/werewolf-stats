const { bindPlayer, getCurrentUser, searchPlayers } = require("../../utils/auth");

function boundPlayersFromUser(user) {
  const explicitPlayers = Array.isArray(user && user.bound_players) ? user.bound_players : [];
  if (explicitPlayers.length) {
    return explicitPlayers;
  }
  const ids = []
    .concat(user && user.player_id ? [user.player_id] : [])
    .concat(Array.isArray(user && user.linked_player_ids) ? user.linked_player_ids : [])
    .filter((item, index, list) => item && list.indexOf(item) === index);
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
    boundPlayerId: "",
    boundPlayers: []
  },

  onShow() {
    const user = getCurrentUser();
    this.setData({
      user,
      boundPlayerId: user && user.player_id ? user.player_id : "",
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
        boundPlayerId: user && user.player_id ? user.player_id : playerId,
        boundPlayers: boundPlayersFromUser(user),
        players
      });
      wx.showToast({ title: "绑定成功", icon: "success" });
    } catch (error) {
      this.setData({ loading: false, error: error.message || "绑定失败" });
    }
  }
});
