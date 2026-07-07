const {
  clearAuth,
  confirmWebLogin,
  getCurrentUser,
  loginWithWechat,
  saveProfile: saveProfileRequest
} = require("../../utils/auth");
const { request } = require("../../utils/api");
const { getSelectedScope, scopeParams } = require("../../utils/scope");

const GENDER_VALUES = ["prefer_not_to_say", "male", "female", "other"];
const GENDER_LABELS = ["不便透露", "男", "女", "其他"];

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
    boundPlayerLabel: ""
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
    const selectedScope = getSelectedScope();
    let centerStatus = "未登录";
    let centerCopy = "登录并绑定选手后，这里会显示你的赛事入口和个人选手页。";
    let boundPlayerLabel = "";
    if (user && user.player_id) {
      centerStatus = "已绑定选手";
      boundPlayerLabel = user.player_id;
      centerCopy = "可以直接进入我的选手页、比赛日详情和预测榜。";
    } else if (user) {
      centerStatus = "未绑定选手";
      centerCopy = "绑定选手后，会显示你的赛事入口和个人选手页。";
    }
    if (!selectedScope || !selectedScope.competition) {
      this.setData({
        selectedScope: null,
        latestDay: null,
        centerStatus,
        boundPlayerLabel,
        centerCopy: user ? "先进入一个赛事，再查看我的比赛日和选手页。" : centerCopy
      });
      return;
    }
    let latestDay = null;
    try {
      const dashboard = await request("/api/dashboard", scopeParams(selectedScope));
      latestDay = (dashboard.match_days || [])[0] || null;
    } catch (error) {
      centerCopy = error.message || "我的赛事数据加载失败。";
    }
    this.setData({
      selectedScope,
      latestDay,
      centerStatus,
      centerCopy,
      boundPlayerLabel
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
      boundPlayerLabel: ""
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
    const user = this.data.user;
    if (!user || !user.player_id) {
      this.setData({ error: "请先绑定选手。" });
      return;
    }
    const selectedScope = getSelectedScope();
    if (!selectedScope || !selectedScope.competition) {
      wx.showModal({
        title: "先选择赛事",
        content: "需要先进入一个赛事，才能查看该赛事范围下的选手页面。",
        confirmText: "去选择",
        success(result) {
          if (result.confirm) {
            wx.switchTab({ url: "/pages/dashboard/dashboard" });
          }
        }
      });
      return;
    }
    wx.navigateTo({
      url: `/pages/player-detail/player-detail?player_id=${encodeURIComponent(user.player_id)}`
    });
  }
});
