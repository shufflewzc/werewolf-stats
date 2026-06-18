const apiPresets = {
  production: "https://wolf.fakerclaw.indevs.in",
  local: "http://127.0.0.1:8000"
};

const activeApiEnv = "local";

module.exports = {
  activeApiEnv,
  allowLocalApi: true,
  apiBaseUrl: apiPresets[activeApiEnv] || apiPresets.production,
  apiPresets
};
