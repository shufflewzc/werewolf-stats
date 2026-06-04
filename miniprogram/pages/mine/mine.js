const {
  bindExistingAccount,
  clearAuth,
  getCurrentUser,
  loginWithWechat
} = require("../../utils/auth");

Page({
  data: {
    loading: false,
    error: "",
    user: null,
    username: "",
    password: ""
  },

  onShow() {
    this.setData({ user: getCurrentUser() });
  },

  async login() {
    this.setData({ loading: true, error: "" });
    try {
      const payload = await loginWithWechat("");
      this.setData({ loading: false, user: payload.user });
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
      this.setData({ loading: false, user: payload.user, password: "" });
      wx.showToast({ title: "绑定成功", icon: "success" });
    } catch (error) {
      this.setData({ loading: false, error: error.message || "绑定失败" });
    }
  },

  logout() {
    clearAuth();
    this.setData({ user: null, username: "", password: "", error: "" });
  }
});
