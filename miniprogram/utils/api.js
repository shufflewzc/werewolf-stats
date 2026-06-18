const { allowLocalApi, apiBaseUrl } = require("../config");

const DEFAULT_TIMEOUT_MS = 12000;
const GET_RETRY_LIMIT = 1;
const AUTH_SESSION_KEY = "werewolf:miniprogramSession";
const AUTH_USER_KEY = "werewolf:miniprogramUser";
let authExpiredModalVisible = false;

class ApiError extends Error {
  constructor(message, options = {}) {
    super(message);
    this.name = "ApiError";
    this.statusCode = options.statusCode || 0;
    this.requestId = options.requestId || "";
    this.code = options.code || "";
    this.retryable = Boolean(options.retryable);
    this.payload = options.payload || null;
  }
}

function normalizeBaseUrl(baseUrl) {
  return String(baseUrl || "").replace(/\/+$/, "");
}

function isLocalBaseUrl(baseUrl) {
  return /^https?:\/\/(127\.0\.0\.1|localhost|0\.0\.0\.0)(:\d+)?/i.test(String(baseUrl || ""));
}

function assertUsableBaseUrl(baseUrl) {
  if (!baseUrl) {
    throw new ApiError("小程序接口地址未配置。");
  }
  if (isLocalBaseUrl(baseUrl) && !allowLocalApi) {
    throw new ApiError("当前小程序仍连接本地服务，请先切换为正式 HTTPS 域名。");
  }
}

function buildQuery(params) {
  const entries = Object.keys(params || {})
    .filter((key) => params[key] !== undefined && params[key] !== null && params[key] !== "")
    .map((key) => `${encodeURIComponent(key)}=${encodeURIComponent(params[key])}`);
  return entries.length ? `?${entries.join("&")}` : "";
}

function headerValue(headers, name) {
  const target = String(name || "").toLowerCase();
  const headerKeys = Object.keys(headers || {});
  const matchedKey = headerKeys.find((key) => String(key).toLowerCase() === target);
  return matchedKey ? headers[matchedKey] : "";
}

function extractRequestId(response) {
  return String(headerValue(response && response.header, "X-Request-ID") || "");
}

function errorMessageFromResponse(response) {
  const data = response && response.data;
  if (data && typeof data === "object") {
    return data.error || data.message || data.detail || "";
  }
  if (typeof data === "string" && data.length < 120) {
    return data;
  }
  return "";
}

function appendRequestId(message, requestId) {
  if (!requestId) {
    return message;
  }
  return `${message}（请求编号 ${requestId}）`;
}

function isAuthExpiredStatus(statusCode, message) {
  return statusCode === 401 || /请先登录|重新登录|登录过期/.test(String(message || ""));
}

function clearStoredAuth() {
  wx.removeStorageSync(AUTH_SESSION_KEY);
  wx.removeStorageSync(AUTH_USER_KEY);
}

function notifyAuthExpired() {
  if (authExpiredModalVisible) {
    return;
  }
  authExpiredModalVisible = true;
  wx.showModal({
    title: "登录已失效",
    content: "请重新微信登录后继续操作。",
    showCancel: false,
    confirmText: "知道了",
    complete() {
      authExpiredModalVisible = false;
    }
  });
}

function shouldRetry(statusCode) {
  return statusCode === 408 || statusCode === 429 || statusCode >= 500;
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function buildApiError(response) {
  const requestId = extractRequestId(response);
  const statusCode = Number((response && response.statusCode) || 0);
  const rawMessage = errorMessageFromResponse(response) || `接口返回 ${statusCode}`;
  const message = appendRequestId(rawMessage, requestId);
  const error = new ApiError(message, {
    statusCode,
    requestId,
    retryable: shouldRetry(statusCode),
    payload: response && response.data
  });
  if (isAuthExpiredStatus(statusCode, rawMessage)) {
    error.code = "AUTH_EXPIRED";
  }
  return error;
}

function buildNetworkError(error) {
  const message = error && error.errMsg ? error.errMsg : "网络请求失败";
  if (message.indexOf("url not in domain list") >= 0) {
    return new ApiError("接口域名未加入微信小程序 request 合法域名，请检查公众平台配置。");
  }
  return new ApiError(message.indexOf("timeout") >= 0 ? "请求超时，请稍后重试。" : message, {
    retryable: true
  });
}

function handleAuthError(error) {
  if (error && error.code === "AUTH_EXPIRED") {
    clearStoredAuth();
    notifyAuthExpired();
  }
}

function wxRequest(options) {
  return new Promise((resolve, reject) => {
    wx.request(Object.assign({}, options, {
      success(response) {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data || {});
          return;
        }
        reject(buildApiError(response));
      },
      fail(error) {
        reject(buildNetworkError(error));
      }
    }));
  });
}

async function requestWithRetry(options, retryLimit) {
  let lastError = null;
  for (let attempt = 0; attempt <= retryLimit; attempt += 1) {
    try {
      return await wxRequest(options);
    } catch (error) {
      lastError = error;
      if (!error.retryable || attempt >= retryLimit) {
        handleAuthError(error);
        throw error;
      }
      await wait(300 * (attempt + 1));
    }
  }
  handleAuthError(lastError);
  throw lastError;
}

function request(path, params = {}) {
  const baseUrl = normalizeBaseUrl(apiBaseUrl);
  assertUsableBaseUrl(baseUrl);
  const url = `${baseUrl}${path}${buildQuery(params)}`;
  return requestWithRetry({
    url,
    method: "GET",
    timeout: DEFAULT_TIMEOUT_MS
  }, GET_RETRY_LIMIT);
}

function encodeForm(data) {
  return Object.keys(data || {})
    .filter((key) => data[key] !== undefined && data[key] !== null)
    .map((key) => `${encodeURIComponent(key)}=${encodeURIComponent(data[key])}`)
    .join("&");
}

function post(path, data = {}) {
  const baseUrl = normalizeBaseUrl(apiBaseUrl);
  assertUsableBaseUrl(baseUrl);
  const url = `${baseUrl}${path}`;
  return requestWithRetry({
    url,
    method: "POST",
    data: encodeForm(data),
    timeout: DEFAULT_TIMEOUT_MS,
    header: {
      "Content-Type": "application/x-www-form-urlencoded"
    }
  }, 0);
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
  ApiError,
  post,
  request,
  assetUrl
};
