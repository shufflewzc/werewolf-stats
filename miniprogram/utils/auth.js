const { post, request } = require("./api");

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

async function saveProfile(profile) {
  const payload = await post("/api/miniprogram/profile", {
    session_token: getSessionToken(),
    display_name: profile.display_name,
    province_name: profile.province_name,
    region_name: profile.region_name,
    gender: profile.gender,
    bio: profile.bio
  });
  wx.setStorageSync(USER_KEY, payload.user || null);
  return payload;
}

function searchPlayers(keyword) {
  return request("/api/miniprogram/player-search", {
    session_token: getSessionToken(),
    q: keyword
  });
}

function getCurrentPlayerForScope(scope) {
  return request("/api/miniprogram/current-player", {
    session_token: getSessionToken(),
    competition: scope && scope.competition,
    season: scope && scope.season
  });
}

async function bindPlayer(playerId) {
  const payload = await post("/api/miniprogram/bind-player", {
    session_token: getSessionToken(),
    player_id: playerId
  });
  wx.setStorageSync(USER_KEY, payload.user || null);
  return payload;
}

async function unbindPlayer(playerId) {
  const payload = await post("/api/miniprogram/unbind-player", {
    session_token: getSessionToken(),
    player_id: playerId
  });
  wx.setStorageSync(USER_KEY, payload.user || null);
  return payload;
}

function extractWebLoginToken(scannedValue) {
  const value = String(scannedValue || "").trim();
  if (!value) {
    return "";
  }
  const match = value.match(/[?&]token=([^&#]+)/);
  if (match) {
    return decodeURIComponent(match[1]);
  }
  return value;
}

function confirmWebLogin(scannedValue) {
  return post("/api/miniprogram/web-login-confirm", {
    session_token: getSessionToken(),
    token: extractWebLoginToken(scannedValue)
  });
}

module.exports = {
  bindPlayer,
  clearAuth,
  confirmWebLogin,
  getCurrentUser,
  getCurrentPlayerForScope,
  getSessionToken,
  loginWithWechat,
  saveProfile,
  searchPlayers,
  unbindPlayer
};
