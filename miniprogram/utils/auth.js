const { post } = require("./api");

const SESSION_KEY = "werewolf:miniprogramSession";
const USER_KEY = "werewolf:miniprogramUser";

function getSessionToken() {
  return wx.getStorageSync(SESSION_KEY) || "";
}

function getCurrentUser() {
  return wx.getStorageSync(USER_KEY) || null;
}

function saveAuth(payload) {
  wx.setStorageSync(SESSION_KEY, payload.session_token || "");
  wx.setStorageSync(USER_KEY, payload.user || null);
}

function clearAuth() {
  wx.removeStorageSync(SESSION_KEY);
  wx.removeStorageSync(USER_KEY);
}

function wxLogin() {
  return new Promise((resolve, reject) => {
    wx.login({
      success(result) {
        if (result.code) {
          resolve(result.code);
          return;
        }
        reject(new Error("微信登录没有返回 code"));
      },
      fail(error) {
        reject(new Error(error.errMsg || "微信登录失败"));
      }
    });
  });
}

async function loginWithWechat(nickname = "") {
  const code = await wxLogin();
  const payload = await post("/api/miniprogram/login", { code, nickname });
  saveAuth(payload);
  return payload;
}

async function bindExistingAccount(username, password) {
  const payload = await post("/api/miniprogram/bind-account", {
    session_token: getSessionToken(),
    username,
    password
  });
  saveAuth(payload);
  return payload;
}

module.exports = {
  bindExistingAccount,
  clearAuth,
  getCurrentUser,
  getSessionToken,
  loginWithWechat
};
