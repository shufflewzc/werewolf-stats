const { apiBaseUrl } = require("../config");

function normalizeBaseUrl(baseUrl) {
  return String(baseUrl || "").replace(/\/+$/, "");
}

function buildQuery(params) {
  const entries = Object.keys(params || {})
    .filter((key) => params[key] !== undefined && params[key] !== null && params[key] !== "")
    .map((key) => `${encodeURIComponent(key)}=${encodeURIComponent(params[key])}`);
  return entries.length ? `?${entries.join("&")}` : "";
}

function request(path, params = {}) {
  const url = `${normalizeBaseUrl(apiBaseUrl)}${path}${buildQuery(params)}`;
  return new Promise((resolve, reject) => {
    wx.request({
      url,
      method: "GET",
      timeout: 12000,
      success(response) {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data || {});
          return;
        }
        reject(new Error(`接口返回 ${response.statusCode}`));
      },
      fail(error) {
        reject(new Error(error.errMsg || "网络请求失败"));
      }
    });
  });
}

function encodeForm(data) {
  return Object.keys(data || {})
    .filter((key) => data[key] !== undefined && data[key] !== null)
    .map((key) => `${encodeURIComponent(key)}=${encodeURIComponent(data[key])}`)
    .join("&");
}

function post(path, data = {}) {
  const url = `${normalizeBaseUrl(apiBaseUrl)}${path}`;
  return new Promise((resolve, reject) => {
    wx.request({
      url,
      method: "POST",
      data: encodeForm(data),
      timeout: 12000,
      header: {
        "Content-Type": "application/x-www-form-urlencoded"
      },
      success(response) {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data || {});
          return;
        }
        const message = response.data && response.data.error ? response.data.error : `接口返回 ${response.statusCode}`;
        reject(new Error(message));
      },
      fail(error) {
        reject(new Error(error.errMsg || "网络请求失败"));
      }
    });
  });
}

function assetUrl(path) {
  if (!path) {
    return "";
  }
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  return `${normalizeBaseUrl(apiBaseUrl)}/${String(path).replace(/^\/+/, "")}`;
}

module.exports = {
  post,
  request,
  assetUrl
};
