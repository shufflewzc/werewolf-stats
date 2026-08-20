const {
  clearAuth,
  confirmWebLogin,
  getCurrentPlayerForScope,
  getCurrentUser,
  loginWithWechat,
  saveProfile: saveProfileRequest
} = require("../../utils/auth");
const { request } = require("../../utils/api");
const { getFollowedPlayers, refreshFollowedPlayers, toggleFollow } = require("../../utils/follows");
const { confirmScopeMismatch, confirmScopeSwitch, getRequiredScope, scopeActivationError, scopeParams } = require("../../utils/scope");

const GENDER_VALUES = ["prefer_not_to_say", "male", "female", "other"];
const GENDER_LABELS = ["不便透露", "男", "女", "其他"];

function boundPlayersFromUser(user) {
  const explicitPlayers = Array.isArray(user && user.bound_players) ? user.bound_players : [];
  if (explicitPlayers.length) {
    return explicitPlayers;
  }
  const ids = []
    .concat(Array.isArray(user && user.bound_player_ids) ? user.bound_player_ids : [])
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
    user: null,
    profile: {
      display_name: "",
      province_name: "广东省",
      region_name: "广州市",
      gender: "prefer_not_to_say",
      bio: ""
    },
    genderLabels: GENDER_LABELS,
    genderLabel: "不便透露",
    selectedScope: null,
    latestDay: null,
    centerStatus: "未登录",
    centerCopy: "登录并绑定选手后，这里会显示你的赛事入口和个人选手页。",
    boundPlayerLabel: "",
    boundPlayers: [],
    currentPlayer: null,
    currentPlayerStatus: "unbound",
    followedPlayers: []
  },

  onShow() {
    this.refreshUser(getCurrentUser());
    this.loadMyCenter();
  },

  refreshUser(user) {
    const gender = (user && user.gender) || "prefer_not_to_say";
    this.setData({
      user,
      profile: {
        display_name: (user && user.display_name) || "",
        province_name: (user && user.province_name) || "广东省",
        region_name: (user && user.region_name) || "广州市",
        gender,
        bio: (user && user.bio) || ""
      },
      genderLabel: GENDER_LABELS[Math.max(0, GENDER_VALUES.indexOf(gender))] || "不便透露"
    });
  },

  async loadMyCenter() {
    const user = getCurrentUser();
    const selectedScope = getRequiredScope();
    let centerStatus = "未登录";
    let centerCopy = "登录并绑定选手后，这里会显示你的赛事入口和个人选手页。";
    let boundPlayerLabel = "";
    const boundPlayers = boundPlayersFromUser(user);
    if (user && boundPlayers.length) {
      centerStatus = "已绑定选手";
      boundPlayerLabel = boundPlayers.map((player) => player.display_name || player.player_id).join("、");
      centerCopy = "可以直接进入我的选手页、比赛日详情和预测榜。";
    } else if (user) {
      centerStatus = "未绑定选手";
      centerCopy = "绑定选手后，会显示你的赛事入口和个人选手页。";
    }
    if (!selectedScope) {
      this.setData({
        selectedScope: null,
        latestDay: null,
        followedPlayers: [],
        centerStatus,
        boundPlayerLabel,
        boundPlayers,
        currentPlayer: null,
        currentPlayerStatus: boundPlayers.length ? "not_in_scope" : "unbound",
        centerCopy: user ? "先选择赛事和赛季，再查看我的比赛日和选手页。" : centerCopy
      });
      return;
    }
    let latestDay = null;
    let currentPlayer = null;
    let currentPlayerStatus = boundPlayers.length ? "not_in_scope" : "unbound";
    try {
      const [dashboard, identity] = await Promise.all([
        request("/api/dashboard", scopeParams(selectedScope)),
        user && boundPlayers.length
          ? getCurrentPlayerForScope(selectedScope)
          : Promise.resolve({ status: currentPlayerStatus, player: null })
      ]);
      latestDay = (dashboard.match_days || [])[0] || null;
      currentPlayerStatus = identity.status || currentPlayerStatus;
      currentPlayer = identity.player || null;
      if (currentPlayerStatus === "matched" && currentPlayer) {
        centerStatus = "本赛季已绑定";
        centerCopy = `${currentPlayer.team_name || "未绑定战队"} · 可进入本赛季个人选手页。`;
      } else if (currentPlayerStatus === "conflict") {
        centerStatus = "绑定需要处理";
        centerCopy = "同一赛季绑定了多个选手，请到网页绑定管理中保留一个。";
      } else if (user && boundPlayers.length) {
        centerStatus = "本赛季未绑定";
        centerCopy = "本赛季暂无已绑定选手，可以绑定对应的赛季档案。";
      }
    } catch (error) {
      const recovery = await confirmScopeMismatch(error, { sourceLabel: "该绑定选手" });
      if (recovery) {
        if (recovery.accepted && !this._scopeMismatchRetried) {
          this._scopeMismatchRetried = true;
          return this.loadMyCenter();
        }
        if (!recovery.accepted) {
          centerCopy = scopeActivationError(recovery);
        } else {
          centerCopy = error.message || "我的赛事数据加载失败。";
        }
      } else {
        centerCopy = error.message || "我的赛事数据加载失败。";
      }
    }
    this._scopeMismatchRetried = false;
    this.setData({
      selectedScope,
      latestDay,
      followedPlayers: getFollowedPlayers(selectedScope),
      centerStatus,
      centerCopy,
      boundPlayerLabel,
      boundPlayers,
      currentPlayer,
      currentPlayerStatus
    });
    refreshFollowedPlayers(selectedScope).then((followedPlayers) => {
      this.setData({ followedPlayers });
    });
  },

  async login() {
    this.setData({ loading: true, error: "" });
    try {
      const payload = await loginWithWechat("");
      this.setData({ loading: false });
      this.refreshUser(payload.user);
      this.loadMyCenter();
      wx.showToast({ title: payload.created ? "已创建账号" : "登录成功", icon: "success" });
    } catch (error) {
      this.setData({ loading: false, error: error.message || "微信登录失败" });
    }
  },

  logout() {
    clearAuth();
    this.setData({
      user: null,
      error: "",
      centerStatus: "未登录",
      centerCopy: "登录并绑定选手后，这里会显示你的赛事入口和个人选手页。",
      boundPlayerLabel: "",
      boundPlayers: [],
      currentPlayer: null,
      currentPlayerStatus: "unbound",
      followedPlayers: []
    });
  },

  updateProfileField(event) {
    const field = event.currentTarget.dataset.field;
    this.setData({
      [`profile.${field}`]: event.detail.value
    });
  },

  updateGender(event) {
    const index = Number(event.detail.value);
    this.setData({
      "profile.gender": GENDER_VALUES[index] || "prefer_not_to_say",
      genderLabel: GENDER_LABELS[index] || "不便透露"
    });
  },

  async saveProfile() {
    this.setData({ loading: true, error: "" });
    try {
      const payload = await saveProfileRequest(this.data.profile);
      this.setData({ loading: false });
      this.refreshUser(payload.user);
      this.loadMyCenter();
      wx.showToast({ title: "资料已保存", icon: "success" });
    } catch (error) {
      this.setData({ loading: false, error: error.message || "资料保存失败" });
    }
  },

  scanWebLogin() {
    if (!this.data.user) {
      this.setData({ error: "请先微信登录。" });
      return;
    }
    wx.scanCode({
      onlyFromCamera: true,
      scanType: ["qrCode"],
      success: async (result) => {
        this.setData({ loading: true, error: "" });
        try {
          const payload = await confirmWebLogin(result.result);
          this.setData({ loading: false });
          wx.showToast({
            title: payload.display_name ? "网页登录已确认" : "确认成功",
            icon: "success"
          });
        } catch (error) {
          this.setData({ loading: false, error: error.message || "网页登录确认失败" });
        }
      },
      fail: (error) => {
        if (error.errMsg && error.errMsg.indexOf("cancel") >= 0) {
          return;
        }
        this.setData({ error: error.errMsg || "扫码失败" });
      }
    });
  },

  goBindPlayer() {
    if (!this.data.user) {
      this.setData({ error: "请先微信登录。" });
      return;
    }
    wx.navigateTo({ url: "/pages/player-bind/player-bind" });
  },

  goCompetitions() {
    wx.switchTab({ url: "/pages/competitions/competitions" });
  },

  openLatestDay() {
    const latestDay = this.data.latestDay;
    if (!latestDay || !latestDay.played_on) {
      this.goCompetitions();
      return;
    }
    wx.navigateTo({
      url: `/pages/day-detail/day-detail?played_on=${encodeURIComponent(latestDay.played_on)}`
    });
  },

  openPrediction() {
    const latestDay = this.data.latestDay;
    if (latestDay && latestDay.played_on) {
      wx.navigateTo({
        url: `/pages/predictions/predictions?played_on=${encodeURIComponent(latestDay.played_on)}`
      });
      return;
    }
    wx.navigateTo({ url: "/pages/predictions/predictions" });
  },

  openMyPlayerPage() {
    const currentPlayer = this.data.currentPlayer;
    if (!currentPlayer || !currentPlayer.player_id) {
      this.setData({
        error: this.data.currentPlayerStatus === "conflict"
          ? "同一赛季绑定了多个选手，请先处理绑定关系。"
          : "本赛季暂无已绑定选手。"
      });
      return;
    }
    const selectedScope = getRequiredScope();
    if (!selectedScope) {
      wx.showModal({
        title: "先选择赛事和赛季",
        content: "需要先选择完整的赛事和赛季，才能查看该赛季的选手页面。",
        confirmText: "去选择",
        success(result) {
          if (result.confirm) {
            wx.switchTab({ url: "/pages/competitions/competitions" });
          }
        }
      });
      return;
    }
    wx.navigateTo({
      url: `/pages/player-detail/player-detail?player_id=${encodeURIComponent(currentPlayer.player_id)}&strict_player_id=1`
    });
  },

  async openBoundPlayerPage(event) {
    const playerId = event.currentTarget.dataset.playerId;
    if (!playerId) {
      return;
    }
    const boundPlayer = this.data.boundPlayers.find((item) => item.player_id === playerId) || {};
    if (!boundPlayer.competition || !boundPlayer.season) {
      this.setData({ error: "该绑定选手缺少赛事和赛季，请先从赛事入口选择。" });
      return;
    }
    const activation = await confirmScopeSwitch({
      competition: boundPlayer.competition,
      season: boundPlayer.season
    }, {
      title: "切换绑定赛季",
      sourceLabel: `绑定选手「${boundPlayer.display_name || playerId}」`
    });
    if (!activation.accepted) {
      this.setData({ error: scopeActivationError(activation) });
      return;
    }
    wx.navigateTo({
      url: `/pages/player-detail/player-detail?player_id=${encodeURIComponent(playerId)}&strict_player_id=1`
    });
  },

  openFollowedPlayer(event) {
    const playerId = event.currentTarget.dataset.playerId;
    if (!playerId || !this.data.selectedScope) {
      return;
    }
    wx.navigateTo({
      url: `/pages/player-detail/player-detail?player_id=${encodeURIComponent(playerId)}`
    });
  },

  removeFollowedPlayer(event) {
    const playerId = event.currentTarget.dataset.playerId;
    const selectedScope = this.data.selectedScope;
    if (!playerId || !selectedScope) {
      return;
    }
    toggleFollow({ player_id: playerId }, selectedScope);
    this.setData({ followedPlayers: getFollowedPlayers(selectedScope) });
    wx.showToast({ title: "已取消关注", icon: "none" });
  }
});
