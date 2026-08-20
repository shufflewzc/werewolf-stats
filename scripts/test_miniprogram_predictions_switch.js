const assert = require("assert");
const Module = require("module");
const path = require("path");

const pagePath = path.resolve(__dirname, "../miniprogram/pages/predictions/predictions.js");
const scope = {
  competition: "测试赛事",
  season: "S2",
  region: "广州",
  series: "jcds"
};
const days = ["2026-08-07", "2026-08-06", "2026-08-05"].map((playedOn) => ({
  played_on: playedOn,
  label: `${playedOn} 比赛日`,
  match_count: 3,
  player_entry_count: 12
}));

function payload(playedOn) {
  const selectedPlayedOn = playedOn || days[0].played_on;
  return {
    scope: {
      label: scope.competition,
      selected_competition: scope.competition,
      selected_season: scope.season
    },
    days,
    selected_day: days.find((item) => item.played_on === selectedPlayedOn),
    predictions: [],
    pagination: { total: 0, has_more: false },
    band_summary: [],
    roster_source: "published_scenario",
    model_metadata: {}
  };
}

let requestImpl = (_apiPath, params) => Promise.resolve(payload(params.played_on));
const requestCalls = [];
let pageDefinition = null;
const originalLoad = Module._load;

Module._load = function mockPageDependencies(request, parent, isMain) {
  if (parent && parent.filename === pagePath && request === "../../utils/api") {
    return {
      request(apiPath, params, options) {
        requestCalls.push({ apiPath, params, options });
        return requestImpl(apiPath, params, options);
      }
    };
  }
  if (parent && parent.filename === pagePath && request === "../../utils/scope") {
    return {
      appendScopeToPath(target) { return target; },
      applyScopeFromOptions() {},
      getRequiredScope() { return scope; },
      goCompetitions() {},
      needsCompetitionState(extra) { return { ...extra, loading: false, needsCompetition: true }; },
      sameScope(left, right) {
        return Boolean(
          left
          && right
          && left.competition === right.competition
          && left.season === right.season
        );
      },
      scopeParams(selectedScope) { return selectedScope; }
    };
  }
  return originalLoad.call(this, request, parent, isMain);
};

global.Page = (definition) => { pageDefinition = definition; };
global.wx = {
  stopPullDownRefresh() {},
  showToast() {},
  navigateTo() {}
};

delete require.cache[pagePath];
require(pagePath);
Module._load = originalLoad;

function createPage() {
  const page = {
    data: JSON.parse(JSON.stringify(pageDefinition.data)),
    setData(update) { Object.assign(this.data, update); }
  };
  Object.keys(pageDefinition).forEach((key) => {
    if (key !== "data") {
      page[key] = pageDefinition[key];
    }
  });
  return page;
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

async function run() {
  const page = createPage();
  page.onLoad({});
  await page.onShow();
  assert.strictEqual(page.data.selectedDay.played_on, "2026-08-07");

  await page.chooseDay({ currentTarget: { dataset: { playedOn: "2026-08-06" } } });
  assert.strictEqual(page.data.selectedDay.played_on, "2026-08-06");

  requestCalls.length = 0;
  await page.onShow();
  assert.strictEqual(requestCalls[0].params.played_on, "2026-08-06");
  assert.strictEqual(page.data.selectedDay.played_on, "2026-08-06");

  const slow = deferred();
  const fast = deferred();
  requestImpl = (_apiPath, params) => (
    params.played_on === "2026-08-05" ? slow.promise : fast.promise
  );
  const slowSwitch = page.chooseDay({ currentTarget: { dataset: { playedOn: "2026-08-05" } } });
  const fastSwitch = page.chooseDay({ currentTarget: { dataset: { playedOn: "2026-08-07" } } });
  fast.resolve(payload("2026-08-07"));
  await fastSwitch;
  slow.resolve(payload("2026-08-05"));
  await slowSwitch;

  assert.strictEqual(page.data.selectedDay.played_on, "2026-08-07");
  assert.strictEqual(page.data.switchingDay, false);
  assert.strictEqual(page.data.switchingPlayedOn, "");
  console.log("小程序比赛日切换回归测试通过。");
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
