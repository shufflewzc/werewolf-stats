const { allowLocalApi, apiBaseUrl } = require("../config");

const DEFAULT_TIMEOUT_MS = 12000;
const GET_RETRY_LIMIT = 1;
const PUBLIC_CACHE_TTL_MS = 60000;
const PUBLIC_CACHE_PREFIX = "werewolf:publicApi:";
const AUTH_SESSION_KEY = "werewolf:miniprogramSession";
const AUTH_USER_KEY = "werewolf:miniprogramUser";
let authExpiredModalVisible = false;
let invalidScopeModalVisible = false;

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
    payload: response && response.data,
    code: String((response && response.data && (response.data.code || response.data.error_code)) || "")
  });
  if (isAuthExpiredStatus(statusCode, rawMessage)) {
    error.code = "AUTH_EXPIRED";
  }
  return error;
}

function shortRequestTarget(options) {
  const url = String((options && options.url) || "");
  if (!url) {
    return "";
  }
  return url.replace(/^https?:\/\/[^/]+/i, "") || url;
}

function buildNetworkError(error, options) {
  const message = error && error.errMsg ? error.errMsg : "网络请求失败";
  const target = shortRequestTarget(options);
  const suffix = target ? `：${target}` : "";
  if (message.indexOf("url not in domain list") >= 0) {
    return new ApiError(`接口域名未加入微信小程序 request 合法域名${suffix}，请检查公众平台配置。`);
  }
  return new ApiError(message.indexOf("timeout") >= 0 ? `请求超时${suffix}，请确认服务已启动后重试。` : message, {
    retryable: true
  });
}

function handleInvalidScope(error) {
  if (!error || !["SCOPE_REQUIRED", "SCOPE_NOT_FOUND"].includes(error.code)) {
    return;
  }
  const { clearSelectedScope } = require("./scope");
  clearSelectedScope();
  if (invalidScopeModalVisible) {
    return;
  }
  invalidScopeModalVisible = true;
  wx.showModal({
    title: "重新选择赛事和赛季",
    content: error.message || "当前赛事或赛季已失效，请重新选择。",
    showCancel: false,
    confirmText: "去选择",
    complete() {
      invalidScopeModalVisible = false;
      wx.switchTab({ url: "/pages/competitions/competitions" });
    }
  });
}

function handleApiError(error) {
  if (error && error.code === "AUTH_EXPIRED") {
    clearStoredAuth();
    notifyAuthExpired();
  }
  handleInvalidScope(error);
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
        reject(buildNetworkError(error, options));
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
        handleApiError(error);
        throw error;
      }
      await wait(300 * (attempt + 1));
    }
  }
  handleApiError(lastError);
  throw lastError;
}

function publicCacheKey(url) {
  return `${PUBLIC_CACHE_PREFIX}${url}`;
}

function getPublicCache(url) {
  try {
    const cached = wx.getStorageSync(publicCacheKey(url));
    if (!cached || !cached.cachedAt || Date.now() - cached.cachedAt > PUBLIC_CACHE_TTL_MS) {
      wx.removeStorageSync(publicCacheKey(url));
      return null;
    }
    return cached.payload || null;
  } catch (error) {
    return null;
  }
}

function setPublicCache(url, payload) {
  try {
    wx.setStorageSync(publicCacheKey(url), { cachedAt: Date.now(), payload });
  } catch (error) {
    // 本地存储不足不应影响公开赛事数据的展示。
  }
}

function removePublicCache(url) {
  try {
    wx.removeStorageSync(publicCacheKey(url));
  } catch (error) {
    // 缓存清理失败不应掩盖真实的 scope 错误。
  }
}

function requiredRequestScope(params = {}) {
  if (String(params.scope_required || "") !== "1") {
    return null;
  }
  const competition = String(params.competition || "").trim();
  const season = String(params.season || "").trim();
  if (!competition || !season) {
    throw new ApiError("请先选择完整的赛事和赛季。", { code: "SCOPE_REQUIRED" });
  }
  return { competition, season };
}

function payloadScope(payload) {
  const scope = payload && typeof payload.scope === "object" ? payload.scope : {};
  return {
    competition: String(scope.competition || scope.selected_competition || "").trim(),
    season: String(scope.season || scope.selected_season || "").trim()
  };
}

function assertPayloadScope(payload, requestedScope) {
  if (!requestedScope) {
    return payload;
  }
  const actualScope = payloadScope(payload);
  if (
    !actualScope.competition
    || !actualScope.season
    || actualScope.competition !== requestedScope.competition
    || actualScope.season !== requestedScope.season
  ) {
    throw new ApiError(
      `赛季响应不一致：请求「${requestedScope.competition} · ${requestedScope.season}」，接口返回「${actualScope.competition || "未提供赛事"} · ${actualScope.season || "未提供赛季"}」。`,
      {
        code: "SCOPE_RESPONSE_MISMATCH",
        payload: {
          requested_scope: requestedScope,
          response_scope: actualScope
        }
      }
    );
  }
  return payload;
}

function isCacheablePublicPath(path) {
  return /^\/api\/(?!miniprogram\/)/.test(String(path || ""));
}

async function request(path, params = {}, options = {}) {
  const baseUrl = normalizeBaseUrl(apiBaseUrl);
  assertUsableBaseUrl(baseUrl);
  let requestedScope = null;
  try {
    requestedScope = requiredRequestScope(params);
  } catch (error) {
    handleApiError(error);
    throw error;
  }
  const url = `${baseUrl}${path}${buildQuery(params)}`;
  const useCache = options.useCache !== false && isCacheablePublicPath(path);
  if (useCache && !options.forceRefresh) {
    const cached = getPublicCache(url);
    if (cached) {
      try {
        return assertPayloadScope(cached, requestedScope);
      } catch (error) {
        removePublicCache(url);
        // 旧服务可能曾把其他赛季的数据缓存到当前 URL；丢弃后立即回源。
      }
    }
  }
  const payload = await requestWithRetry({
    url,
    method: "GET",
    timeout: DEFAULT_TIMEOUT_MS
  }, GET_RETRY_LIMIT);
  try {
    assertPayloadScope(payload, requestedScope);
  } catch (error) {
    removePublicCache(url);
    handleApiError(error);
    throw error;
  }
  if (useCache) {
    setPublicCache(url, payload);
  }
  return payload;
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
  assertPayloadScope,
  post,
  request,
  assetUrl
};
