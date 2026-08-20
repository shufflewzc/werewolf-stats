const assert = require("assert");
const Module = require("module");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const scopePath = path.join(ROOT, "miniprogram/utils/scope.js");
const apiPath = path.join(ROOT, "miniprogram/utils/api.js");
const dashboardPagePath = path.join(ROOT, "miniprogram/pages/dashboard/dashboard.js");
const comparePagePath = path.join(ROOT, "miniprogram/pages/compare/compare.js");
const playersPagePath = path.join(ROOT, "miniprogram/pages/players/players.js");
const playerDetailPagePath = path.join(ROOT, "miniprogram/pages/player-detail/player-detail.js");
const predictionsPagePath = path.join(ROOT, "miniprogram/pages/predictions/predictions.js");
const dayDetailPagePath = path.join(ROOT, "miniprogram/pages/day-detail/day-detail.js");
const shareCardPagePath = path.join(ROOT, "miniprogram/pages/share-card/share-card.js");

const STORAGE_KEY = "werewolf:selectedCompetition";
const PUBLIC_CACHE_PREFIX = "werewolf:publicApi:";
const S1 = {
  competition: "测试赛事",
  season: "S1",
  region: "广州",
  series: "test-series",
  seriesName: "测试系列赛"
};
const S2 = { ...S1, season: "S2" };

const storage = new Map();
const modalCalls = [];
const modalResults = [];
const switchTabCalls = [];
const networkCalls = [];
let networkImpl = null;

global.wx = {
  getStorageSync(key) {
    return storage.has(key) ? storage.get(key) : null;
  },
  setStorageSync(key, value) {
    storage.set(key, value);
  },
  removeStorageSync(key) {
    storage.delete(key);
  },
  showModal(options) {
    modalCalls.push(options);
    const result = modalResults.length ? modalResults.shift() : { confirm: true, cancel: false };
    if (options.success) options.success(result);
    if (options.complete) options.complete(result);
  },
  switchTab(options) {
    switchTabCalls.push(options);
  },
  request(options) {
    networkCalls.push(options);
    if (!networkImpl) {
      throw new Error("测试未配置 wx.request 响应");
    }
    networkImpl(options);
  },
  stopPullDownRefresh() {}
};
global.wx.setNavigationBarTitle = () => {};
global.wx.navigateTo = () => {};

function resetState() {
  storage.clear();
  modalCalls.length = 0;
  modalResults.length = 0;
  switchTabCalls.length = 0;
  networkCalls.length = 0;
  networkImpl = null;
}

function loadFresh(modulePath) {
  delete require.cache[require.resolve(modulePath)];
  return require(modulePath);
}

function cachedPublicKeys() {
  return [...storage.keys()].filter((key) => String(key).startsWith(PUBLIC_CACHE_PREFIX));
}

async function testScopeStorageAndConfirmation() {
  resetState();
  const scope = loadFresh(scopePath);

  const selected = scope.setSelectedScope(S1);
  assert.strictEqual(selected.competition, S1.competition);
  assert.strictEqual(selected.season, "S1");
  assert.strictEqual(scope.getRequiredScope().season, "S1");

  assert.strictEqual(scope.setSelectedScope({ competition: S1.competition }), null);
  assert.strictEqual(scope.getRequiredScope().season, "S1", "partial scope 不得覆盖已选 S1");
  assert.deepStrictEqual(
    scope.scopeParams({ competition: S1.competition }),
    { scope_required: "1" },
    "partial scope 必须 fail closed"
  );

  storage.set(STORAGE_KEY, { competition: S1.competition, season: "" });
  assert.strictEqual(scope.getRequiredScope(), null);
  assert.strictEqual(storage.has(STORAGE_KEY), false, "旧版 partial storage 应被清理");

  scope.setSelectedScope(S1);
  const noOptions = await scope.applyScopeFromOptions({ player_id: "player-s1" });
  assert.strictEqual(noOptions.accepted, true);
  assert.strictEqual(noOptions.status, "none");
  assert.strictEqual(scope.getRequiredScope().season, "S1");

  const partial = await scope.applyScopeFromOptions({ competition: S1.competition });
  assert.strictEqual(partial.accepted, false);
  assert.strictEqual(partial.status, "invalid");
  assert.strictEqual(scope.getRequiredScope().season, "S1");
  assert.strictEqual(modalCalls.length, 0);

  const same = await scope.applyScopeFromOptions({ competition: S1.competition, season: "S1" });
  assert.strictEqual(same.accepted, true);
  assert.strictEqual(same.status, "same");
  assert.strictEqual(modalCalls.length, 0);

  modalResults.push({ confirm: false, cancel: true });
  const cancelled = await scope.applyScopeFromOptions(
    { competition: S2.competition, season: S2.season, region: S2.region, series: S2.series },
    { sourceLabel: "分享的选手详情" }
  );
  assert.strictEqual(cancelled.accepted, false);
  assert.strictEqual(cancelled.status, "cancelled");
  assert.strictEqual(scope.getRequiredScope().season, "S1");
  assert.ok(modalCalls[0].content.includes("分享的选手详情"));
  assert.ok(modalCalls[0].content.includes("S1"));
  assert.ok(modalCalls[0].content.includes("S2"));

  modalResults.push({ confirm: true, cancel: false });
  networkImpl = (options) => options.success({
    statusCode: 200,
    header: {},
    data: {
      cards: [{
        competition_name: S2.competition,
        region_name: "目录广州",
        series_name: S2.seriesName,
        competition_href: `/competitions?competition=${encodeURIComponent(S2.competition)}&series=${S2.series}`,
        seasons: ["S2", "S1"]
      }]
    }
  });
  const switched = await scope.applyScopeFromOptions(
    { competition: S2.competition, season: S2.season, region: "链接旧地区", series: S2.series },
    { sourceLabel: "分享的选手详情" }
  );
  assert.strictEqual(switched.accepted, true);
  assert.strictEqual(switched.status, "switched");
  assert.strictEqual(scope.getRequiredScope().season, "S2");
  assert.strictEqual(scope.getRequiredScope().region, "目录广州", "跨季切换必须使用赛事目录元数据");

  const card = {
    competition_name: S1.competition,
    region_name: S1.region,
    series_name: S1.seriesName,
    competition_href: `/competitions?competition=${encodeURIComponent(S1.competition)}&series=${S1.series}`,
    seasons: ["S2", "S1"],
    selectedSeason: "S1"
  };
  assert.strictEqual(scope.buildScopeFromCompetition(card, "S1").season, "S1");
  assert.strictEqual(scope.buildScopeFromCompetition({ ...card, selectedSeason: "" }, ""), null);
}

async function testApiScopeValidationAndCaching() {
  resetState();
  const scope = loadFresh(scopePath);
  const api = loadFresh(apiPath);
  scope.setSelectedScope(S1);

  networkImpl = (options) => options.success({
    statusCode: 200,
    header: {},
    data: { scope: { competition: S1.competition, season: S1.season }, players: [] }
  });
  const matched = await api.request("/api/players", scope.scopeParams(S1));
  assert.strictEqual(matched.scope.season, "S1");
  assert.strictEqual(networkCalls.length, 1);
  assert.strictEqual(cachedPublicKeys().length, 1, "校验通过后才可写入公开缓存");

  const staleKey = cachedPublicKeys()[0];
  storage.set(staleKey, {
    cachedAt: Date.now(),
    payload: { scope: { competition: S2.competition, season: S2.season }, players: [] }
  });
  networkCalls.length = 0;
  networkImpl = (options) => options.success({
    statusCode: 200,
    header: {},
    data: { scope: { competition: S1.competition, season: S1.season }, players: [] }
  });
  const refreshed = await api.request("/api/players", scope.scopeParams(S1));
  assert.strictEqual(refreshed.scope.season, "S1");
  assert.strictEqual(networkCalls.length, 1, "旧缓存 scope mismatch 必须丢弃并回源");

  resetState();
  const freshScope = loadFresh(scopePath);
  const freshApi = loadFresh(apiPath);
  freshScope.setSelectedScope(S1);
  networkImpl = (options) => options.success({
    statusCode: 200,
    header: {},
    data: { scope: { competition: S2.competition, season: S2.season }, players: [] }
  });
  await assert.rejects(
    freshApi.request("/api/players", freshScope.scopeParams(S1)),
    (error) => error && error.code === "SCOPE_RESPONSE_MISMATCH"
  );
  assert.strictEqual(networkCalls.length, 1);
  assert.strictEqual(cachedPublicKeys().length, 0, "scope mismatch 响应不得入缓存");
  assert.strictEqual(freshScope.getRequiredScope().season, "S1", "响应 mismatch 不得静默改写已选赛季");

  resetState();
  const incompleteScope = loadFresh(scopePath);
  const incompleteApi = loadFresh(apiPath);
  incompleteScope.setSelectedScope(S1);
  await assert.rejects(
    incompleteApi.request("/api/players", incompleteScope.scopeParams({ competition: S1.competition })),
    (error) => error && error.code === "SCOPE_REQUIRED"
  );
  assert.strictEqual(networkCalls.length, 0, "partial scope 必须在发请求前失败");
  assert.strictEqual(incompleteScope.getRequiredScope(), null, "服务端要求重选时清理无效本地 scope");

  resetState();
  const unscopedApi = loadFresh(apiPath);
  networkImpl = (options) => options.success({ statusCode: 200, header: {}, data: { cards: [] } });
  const competitions = await unscopedApi.request("/api/competitions", {});
  assert.deepStrictEqual(competitions.cards, []);
  assert.strictEqual(networkCalls.length, 1, "赛事选择入口允许无 scope 请求");
}

function createPage(definition) {
  const page = {
    data: JSON.parse(JSON.stringify(definition.data)),
    setData(update) {
      Object.assign(this.data, update);
    }
  };
  Object.keys(definition).forEach((key) => {
    if (key !== "data") page[key] = definition[key];
  });
  return page;
}

function loadPageWithApi(pagePath, requestImpl) {
  let definition = null;
  const originalLoad = Module._load;
  Module._load = function mockDependencies(request, parent, isMain) {
    if (parent && parent.filename === pagePath && request === "../../utils/api") {
      return {
        request: requestImpl,
        assetUrl(value) { return value || ""; }
      };
    }
    return originalLoad.call(this, request, parent, isMain);
  };
  global.Page = (value) => { definition = value; };
  delete require.cache[pagePath];
  try {
    require(pagePath);
  } finally {
    Module._load = originalLoad;
  }
  assert.ok(definition, `${path.basename(pagePath)} Page 定义未加载`);
  return createPage(definition);
}

function loadPlayersPage(requestImpl) {
  let definition = null;
  const originalLoad = Module._load;
  Module._load = function mockDependencies(request, parent, isMain) {
    if (parent && parent.filename === playersPagePath && request === "../../utils/api") {
      return {
        request: requestImpl,
        assetUrl(value) { return value || ""; }
      };
    }
    return originalLoad.call(this, request, parent, isMain);
  };
  global.Page = (value) => { definition = value; };
  delete require.cache[playersPagePath];
  require(playersPagePath);
  Module._load = originalLoad;
  assert.ok(definition, "players Page 定义未加载");
  return createPage(definition);
}

function loadPlayerDetailPage(requestImpl) {
  let definition = null;
  const originalLoad = Module._load;
  Module._load = function mockDependencies(request, parent, isMain) {
    if (parent && parent.filename === playerDetailPagePath && request === "../../utils/api") {
      return {
        request: requestImpl,
        assetUrl(value) { return value || ""; }
      };
    }
    return originalLoad.call(this, request, parent, isMain);
  };
  global.Page = (value) => { definition = value; };
  delete require.cache[playerDetailPagePath];
  require(playerDetailPagePath);
  Module._load = originalLoad;
  assert.ok(definition, "player-detail Page 定义未加载");
  return createPage(definition);
}

async function testPlayersPageDoesNotRequestWithoutCompleteScope() {
  resetState();
  loadFresh(scopePath);
  let requestCount = 0;
  const page = loadPlayersPage(async () => {
    requestCount += 1;
    return {};
  });
  await page.loadData();
  assert.strictEqual(requestCount, 0);
  assert.strictEqual(page.data.needsCompetition, true);

  storage.set(STORAGE_KEY, { competition: S1.competition, season: "" });
  const partialPage = loadPlayersPage(async () => {
    requestCount += 1;
    return {};
  });
  await partialPage.loadData();
  assert.strictEqual(requestCount, 0, "partial storage 不得触发选手请求");
  assert.strictEqual(storage.has(STORAGE_KEY), false);
}

async function testSharedPlayerScopeMustBeConfirmedBeforeRequest() {
  resetState();
  const scope = loadFresh(scopePath);
  scope.setSelectedScope(S1);
  let requestCount = 0;
  const page = loadPlayerDetailPage(async () => {
    requestCount += 1;
    return {};
  });
  page.setData({ playerId: "player-s2", strictPlayerId: true });
  modalResults.push({ confirm: false, cancel: true });
  await page.activateScopeAndLoad({
    player_id: "player-s2",
    strict_player_id: "1",
    competition: S2.competition,
    season: S2.season,
    region: S2.region,
    series: S2.series
  });
  assert.strictEqual(requestCount, 0, "取消分享赛季切换后不得请求选手详情");
  assert.strictEqual(scope.getRequiredScope().season, "S1");
  assert.ok(page.data.error.includes("取消"));

  resetState();
  const noScopePage = loadPlayerDetailPage(async () => {
    requestCount += 1;
    return {};
  });
  noScopePage.setData({ playerId: "player-s1", strictPlayerId: true });
  await noScopePage.loadData();
  assert.strictEqual(requestCount, 0, "无完整 scope 时详情页不得发请求");
  assert.strictEqual(noScopePage.data.needsCompetition, true);
}

async function testDashboardAndCompareBlockUnacceptedDeepLinks() {
  resetState();
  const scope = loadFresh(scopePath);
  scope.setSelectedScope(S1);
  let dashboardRequests = 0;
  const dashboard = loadPageWithApi(dashboardPagePath, async () => {
    dashboardRequests += 1;
    return {};
  });
  dashboard.onLoad({ competition: S2.competition });
  await dashboard.onShow();
  assert.strictEqual(dashboardRequests, 0, "dashboard partial scope 不得沿用旧 scope 请求");
  assert.strictEqual(scope.getRequiredScope().season, "S1");
  assert.ok(dashboard.data.error.includes("缺少完整"));

  resetState();
  const compareScope = loadFresh(scopePath);
  compareScope.setSelectedScope(S1);
  let compareRequests = 0;
  const partialCompare = loadPageWithApi(comparePagePath, async () => {
    compareRequests += 1;
    return {};
  });
  await partialCompare.onLoad({
    type: "player",
    left_id: "left-s2",
    competition: S2.competition
  });
  assert.strictEqual(compareRequests, 0, "compare partial scope 不得请求");
  assert.strictEqual(compareScope.getRequiredScope().season, "S1");

  const cancelledCompare = loadPageWithApi(comparePagePath, async () => {
    compareRequests += 1;
    return {};
  });
  modalResults.push({ confirm: false, cancel: true });
  await cancelledCompare.onLoad({
    type: "player",
    left_id: "left-s2",
    right_id: "right-s2",
    competition: S2.competition,
    season: S2.season
  });
  assert.strictEqual(compareRequests, 0, "取消 compare 跨季确认后不得请求");
  assert.strictEqual(compareScope.getRequiredScope().season, "S1");

  cancelledCompare.setData({
    selectedScope: compareScope.getRequiredScope(),
    type: "player",
    left: { id: "left-s1", title: "左选手" },
    right: { id: "right-s1", title: "右选手" }
  });
  const shared = cancelledCompare.onShareAppMessage();
  assert.ok(shared.path.includes("left_id=left-s1"));
  assert.ok(shared.path.includes("right_id=right-s1"));
  assert.ok(shared.path.includes(`competition=${encodeURIComponent(S1.competition)}`));
  assert.ok(shared.path.includes("season=S1"), "compare 分享必须携带 season");
}

async function testPaginationRejectsResponsesAfterScopeSwitch() {
  resetState();
  const scope = loadFresh(scopePath);
  scope.setSelectedScope(S1);

  let resolvePlayers;
  const players = loadPageWithApi(playersPagePath, () => new Promise((resolve) => { resolvePlayers = resolve; }));
  players.setData({
    selectedScope: scope.getRequiredScope(),
    players: [{ player_id: "s1-old" }],
    visiblePlayers: [{ player_id: "s1-old" }],
    playerVisibleCount: 1,
    playerTotalCount: 2,
    playerHasMore: true,
    loadingMore: false
  });
  const playersPending = players.loadMorePlayers();
  scope.setSelectedScope(S2);
  resolvePlayers({ players: [{ player_id: "s1-late" }], pagination: { total: 2, has_more: false } });
  assert.strictEqual(await playersPending, false);
  assert.deepStrictEqual(players.data.players.map((item) => item.player_id), ["s1-old"], "players 不得拼接旧季慢回包");

  scope.setSelectedScope(S1);
  let resolvePredictions;
  const predictions = loadPageWithApi(predictionsPagePath, () => new Promise((resolve) => { resolvePredictions = resolve; }));
  predictions.setData({
    selectedScope: scope.getRequiredScope(),
    selectedDay: { played_on: "2026-08-20" },
    predictions: [{ player_id: "s1-old" }],
    predictionVisibleCount: 1,
    predictionTotalCount: 2,
    predictionHasMore: true,
    loadingMore: false
  });
  const predictionsPending = predictions.loadMorePredictions();
  scope.setSelectedScope(S2);
  resolvePredictions({ predictions: [{ player_id: "s1-late" }], pagination: { total: 2, has_more: false } });
  assert.strictEqual(await predictionsPending, false);
  assert.deepStrictEqual(predictions.data.predictions.map((item) => item.player_id), ["s1-old"], "predictions 不得拼接旧季慢回包");

  scope.setSelectedScope(S1);
  let resolveDayPredictions;
  const dayDetail = loadPageWithApi(dayDetailPagePath, () => new Promise((resolve) => { resolveDayPredictions = resolve; }));
  dayDetail.setData({
    selectedScope: scope.getRequiredScope(),
    playedOn: "2026-08-20",
    predictions: [{ player_id: "s1-old" }],
    visiblePredictions: [{ player_id: "s1-old" }],
    predictionVisibleCount: 1,
    predictionTotalCount: 2,
    predictionHasMore: true
  });
  const dayPending = dayDetail.loadMorePredictions();
  scope.setSelectedScope(S2);
  resolveDayPredictions({ predictions: [{ player_id: "s1-late" }], pagination: { total: 2, has_more: false } });
  assert.strictEqual(await dayPending, false);
  assert.deepStrictEqual(dayDetail.data.predictions.map((item) => item.player_id), ["s1-old"], "day-detail 不得拼接旧季慢回包");
}

function testPlayerShareCodeCarriesScope() {
  resetState();
  global.Page = () => {};
  delete require.cache[shareCardPagePath];
  const { buildPlayerShareCodeUrl } = require(shareCardPagePath);
  const url = new URL(buildPlayerShareCodeUrl("player-s1", S1));
  assert.strictEqual(url.searchParams.get("share_type"), "player");
  assert.strictEqual(url.searchParams.get("player_id"), "player-s1");
  assert.strictEqual(url.searchParams.get("competition"), S1.competition);
  assert.strictEqual(url.searchParams.get("season"), "S1");
  assert.throws(
    () => buildPlayerShareCodeUrl("player-s1", { competition: S1.competition }),
    /完整的选手、赛事和赛季/
  );
}

async function run() {
  await testScopeStorageAndConfirmation();
  await testApiScopeValidationAndCaching();
  await testPlayersPageDoesNotRequestWithoutCompleteScope();
  await testSharedPlayerScopeMustBeConfirmedBeforeRequest();
  await testDashboardAndCompareBlockUnacceptedDeepLinks();
  await testPaginationRejectsResponsesAfterScopeSwitch();
  testPlayerShareCodeCarriesScope();
  console.log("小程序赛事赛季 scope 回归测试通过。");
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
