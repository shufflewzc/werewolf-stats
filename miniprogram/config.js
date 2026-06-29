const apiPresets = {
  production: "https://wolf.metauniverse-cn.xyz",
  local: "http://127.0.0.1:8000"
};

const activeApiEnv = "production";

module.exports = {
  activeApiEnv,
  allowLocalApi: true,
  apiBaseUrl: apiPresets[activeApiEnv] || apiPresets.production,
  apiPresets
};
