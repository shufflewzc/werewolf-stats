const {
  bindExistingAccount,
  clearAuth,
  getCurrentUser,
  loginWithWechat,
  saveProfile: saveProfileRequest
} = require("../../utils/auth");

const GENDER_VALUES = ["prefer_not_to_say", "male", "female", "other"];

Page({
  data: {
    loading: false,
    error: "",
    user: null,
    username: "",
    password: "",
    profile: {
      display_name: "",
      province_name: "广东省",
      region_name: "广州市",
      gender: "prefer_not_to_say",
      bio: "",
      player_id: ""
    }
  },

  onShow() {
    this.refreshUser(getCurrentUser());
  },

  refreshUser(user) {
    this.setData({
      user,
      profile: {
        display_name: (user && user.display_name) || "",
        province_name: (user && user.province_name) || "广东省",
        region_name: (user && user.region_name) || "广州市",
        gender: (user && user.gender) || "prefer_not_to_say",
        bio: (user && user.bio) || "",
        player_id: (user && user.player_id) || ""
      }
    });
  },

  async login() {
    this.setData({ loading: true, error: "" });
    try {
      const payload = await loginWithWechat("");
      this.setData({ loading: false });
      this.refreshUser(payload.user);
      wx.showToast({ title: payload.created ? "已创建账号" : "登录成功", icon: "success" });
    } catch (error) {
      this.setData({ loading: false, error: error.message || "微信登录失败" });
    }
  },

  updateUsername(event) {
    this.setData({ username: event.detail.value });
  },

  updatePassword(event) {
    this.setData({ password: event.detail.value });
  },

  async bindAccount() {
    if (!this.data.username || !this.data.password) {
      this.setData({ error: "请输入网站账号和密码。" });
      return;
    }
    this.setData({ loading: true, error: "" });
    try {
      const payload = await bindExistingAccount(this.data.username, this.data.password);
      this.setData({ loading: false, password: "" });
      this.refreshUser(payload.user);
      wx.showToast({ title: "绑定成功", icon: "success" });
    } catch (error) {
      this.setData({ loading: false, error: error.message || "绑定失败" });
    }
  },

  logout() {
    clearAuth();
    this.setData({ user: null, username: "", password: "", error: "" });
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
      "profile.gender": GENDER_VALUES[index] || "prefer_not_to_say"
    });
  },

  async saveProfile() {
    this.setData({ loading: true, error: "" });
    try {
      const payload = await saveProfileRequest(this.data.profile);
      this.setData({ loading: false });
      this.refreshUser(payload.user);
      wx.showToast({ title: "资料已保存", icon: "success" });
    } catch (error) {
      this.setData({ loading: false, error: error.message || "资料保存失败" });
    }
  }
});
