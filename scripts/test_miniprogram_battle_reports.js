const assert = require('assert');
const Module = require('module');
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
let scope = { competition: '赛事甲', season: 'S1' };
let requestImpl;
let calls = [];
let pageDefinition;
global.Page = definition => { pageDefinition = definition; };
global.wx = { navigateTo: options => calls.push(options.url), stopPullDownRefresh() {} };
const originalLoad = Module._load;
Module._load = function(name, ...args) {
  if (name === '../../utils/api') return { request: (...params) => requestImpl(...params), assetUrl: value => value || '' };
  if (name === '../../utils/scope') return {
    getRequiredScope: () => scope, scopeParams: s => ({ ...s, scope_required: '1' }),
    sameScope: (a, b) => Boolean(a && b && a.competition === b.competition && a.season === b.season),
    goCompetitions() {}, needsCompetitionState: extra => ({ loading: false, needsCompetition: true, selectedScope: null, ...extra }),
    appendScopeToPath: (url, s) => `${url}&competition=${s.competition}&season=${s.season}`
  };
  return originalLoad.call(this, name, ...args);
};
require('../miniprogram/pages/battle-reports/battle-reports');
Module._load = originalLoad;
function page() { return { ...pageDefinition, data: structuredClone(pageDefinition.data), setData(values) {
  for (const [key,value] of Object.entries(values)) {
    const parts = key.replace(/\[(\d+)\]/g, '.$1').split('.');
    let dest = this.data; for (const part of parts.slice(0,-1)) dest = dest[part];
    dest[parts.at(-1)] = value;
  }
} }; }
const report = day => ({ played_on: day, sections: [{ stage: 'regular', matches: [{ match_id: 'm1', mvp: { photo: '/photo.jpg' } }] }] });
const payload = (day, more=false) => ({ reports: [report(day)], pagination: { total: 2, has_more: more } });
(async () => {
  const p = page();
  scope = null;
  requestImpl = () => { throw Error('must not request without scope'); };
  await p.onShow(); assert(p.data.needsCompetition);
  scope = { competition: '赛事甲', season: 'S1' };
  requestImpl = async (url, params) => { assert.equal(url, '/api/battle-reports'); assert.equal(params.scope_required,'1'); return payload('2026-09-10',true); };
  await p.onShow(); assert.equal(p.data.reports.length,1); assert(p.data.hasReports);
  requestImpl = async () => { throw Error('network failed'); };
  await p.loadMore(); assert.equal(p.data.reports.length,1); assert(p.data.error);
  requestImpl = async (url, params) => { assert.equal(params.offset,1); return payload('2026-09-09'); };
  await p.loadMore(); assert.equal(p.data.reports.length,2); assert(!p.data.hasMore);
  p.onImageError({ currentTarget: { dataset: { day: 0, section: 0, match: 0, field: 'photoUrl', id: 'm1' } } });
  assert.equal(p.data.reports[0].sections[0].matches[0].photoUrl,'');
  p.openMatch({ currentTarget: { dataset: { id: 'm1' } } });
  p.openDay({ currentTarget: { dataset: { day: '2026-09-10' } } });
  assert(calls.every(url => url.includes('season=S1')));
  let resolveOld;
  requestImpl = () => new Promise(resolve => { resolveOld = resolve; });
  const oldLoad = p.onShow();
  scope = { competition: '赛事甲', season: 'S2' };
  requestImpl = async () => payload('2026-09-11');
  await p.onShow(); resolveOld(payload('old')); await oldLoad;
  assert.equal(p.data.reports[0].played_on,'2026-09-11');
  let resolveFirst;
  requestImpl = () => new Promise(resolve => { resolveFirst = resolve; });
  const firstRefresh = p.retry();
  requestImpl = async () => payload('newest');
  await p.retry(); resolveFirst(payload('stale')); await firstRefresh;
  assert.equal(p.data.reports[0].played_on,'newest');
  const app = JSON.parse(fs.readFileSync(path.join(root,'miniprogram/app.json')));
  assert.deepEqual(app.tabBar.list.map(item => item.text),['首页','赛事','战报','选手','我的']);
  for (const name of ['dashboard','guild-detail','team-detail']) {
    const source = fs.readFileSync(path.join(root,`miniprogram/pages/${name}/${name}.js`),'utf8');
    assert(!source.includes('switchTab({ url: "/pages/guilds/guilds"'));
  }
  console.log('Battle report frontend: scope, race, paging, retry, images and navigation passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
