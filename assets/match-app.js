(function () {
  const bootstrap = window.__WEREWOLF_MATCH_BOOTSTRAP__ || {};
  const root = document.getElementById("match-app");

  if (!root) {
    return;
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function renderError(message) {
    const legacyHref = bootstrap.legacyHref || "#";
    root.innerHTML = `
      <div class="alert alert-danger mb-0">
        <div class="fw-semibold mb-2">比赛详情加载失败</div>
        <div>${escapeHtml(message || "unknown error")}</div>
        <div class="mt-3">
          <a class="btn btn-outline-dark btn-sm" href="${escapeHtml(legacyHref)}">打开旧版比赛页</a>
        </div>
      </div>
    `;
  }

  async function loadMatchPage() {
    const endpoint = `${bootstrap.apiEndpoint || ""}${window.location.search || ""}`;
    try {
      const response = await fetch(endpoint, {
        headers: {
          Accept: "application/json",
        },
      });
      const payload = await response.json();
      if (!response.ok || payload.error) {
        throw new Error(payload.error || `HTTP ${response.status}`);
      }
      if (payload.title) {
        document.title = payload.title;
      }
      root.innerHTML = payload.body_html || "";
    } catch (error) {
      renderError(error instanceof Error ? error.message : "unknown error");
    }
  }

  loadMatchPage();
})();
