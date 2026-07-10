const { request, assetUrl } = require("../../utils/api");
const { getRequiredScope, goCompetitions, needsCompetitionState, scopeParams } = require("../../utils/scope");

function text(value) {
  const result = String(value === undefined || value === null ? "--" : value).trim();
  return result || "--";
}

function decorate(item, type) {
  return {
    ...item,
    id: String(type === "team" ? item.team_id : item.player_id),
    title: type === "team" ? (item.short_name || item.name || item.team_id) : (item.display_name || item.name || item.player_id),
    meta: type === "team" ? `${item.matches_represented || 0} 场 · ${item.win_rate || "--"}` : `${item.team_name || "未绑定战队"} · ${item.games_played || 0} 局`,
    imageUrl: assetUrl(type === "team" ? item.logo : item.photo)
  };
}

function rowsFrom(leftPayload, rightPayload) {
  const leftMetrics = Array.isArray(leftPayload.metrics) ? leftPayload.metrics : [];
  const rightMetrics = Array.isArray(rightPayload.metrics) ? rightPayload.metrics : [];
  const labels = [];
  leftMetrics.concat(rightMetrics).forEach((item) => {
    const label = String(item.label || "").trim();
    if (label && labels.indexOf(label) < 0) labels.push(label);
  });
  return labels.slice(0, 8).map((label) => {
    const left = leftMetrics.find((item) => String(item.label || "") === label) || {};
    const right = rightMetrics.find((item) => String(item.label || "") === label) || {};
    return { label, leftValue: text(left.value), rightValue: text(right.value), leftCopy: text(left.copy), rightCopy: text(right.copy) };
  });
}

Page({
  data: { loading: true, error: "", needsCompetition: false, selectedScope: null, type: "player", typeLabel: "选手", candidates: [], candidateLabels: [], leftIndex: 0, rightIndex: 0, left: null, right: null, compareRows: [] },

  onLoad(options) {
    this.initialType = options.type === "team" ? "team" : "player";
    this.initialLeftId = decodeURIComponent(options.left_id || "");
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData({ forceRefresh: true }).finally(() => wx.stopPullDownRefresh());
  },

  async loadData(options = {}) {
    this.setData({ loading: true, error: "" });
    try {
      const selectedScope = getRequiredScope();
      if (!selectedScope) {
        this.setData(needsCompetitionState({ candidates: [], candidateLabels: [], left: null, right: null, compareRows: [] }));
        return;
      }
      const type = this.initialType || this.data.type;
      const listPayload = await request(type === "team" ? "/api/teams" : "/api/players", type === "team" ? scopeParams(selectedScope) : { ...scopeParams(selectedScope), limit: 100, offset: 0 }, options);
      const candidates = (type === "team" ? listPayload.teams : listPayload.players || []).map((item) => decorate(item, type));
      if (candidates.length < 2) {
        this.setData({ loading: false, selectedScope, needsCompetition: false, type, typeLabel: type === "team" ? "战队" : "选手", candidates, candidateLabels: candidates.map((item) => item.title), left: null, right: null, compareRows: [], error: `当前赛事至少需要两${type === "team" ? "支战队" : "名选手"}才能对比。` });
        return;
      }
      const preferredLeft = this.initialLeftId || (this.data.left && this.data.left.id) || candidates[0].id;
      const leftIndex = Math.max(0, candidates.findIndex((item) => item.id === preferredLeft));
      let rightIndex = candidates.findIndex((item) => item.id === (this.data.right && this.data.right.id));
      if (rightIndex < 0 || rightIndex === leftIndex) rightIndex = leftIndex === 0 ? 1 : 0;
      this.initialLeftId = "";
      await this.loadComparison({ selectedScope, type, candidates, leftIndex, rightIndex, options });
    } catch (error) {
      this.setData({ loading: false, error: error.message || "对比数据加载失败" });
    }
  },

  async loadComparison({ selectedScope, type, candidates, leftIndex, rightIndex, options = {} }) {
    this.setData({ loading: true, error: "" });
    const endpoint = type === "team" ? "/api/teams/" : "/api/players/";
    const [leftPayload, rightPayload] = await Promise.all([
      request(`${endpoint}${encodeURIComponent(candidates[leftIndex].id)}`, scopeParams(selectedScope), options),
      request(`${endpoint}${encodeURIComponent(candidates[rightIndex].id)}`, scopeParams(selectedScope), options)
    ]);
    this.setData({ loading: false, selectedScope, needsCompetition: false, type, typeLabel: type === "team" ? "战队" : "选手", candidates, candidateLabels: candidates.map((item) => item.title), leftIndex, rightIndex, left: decorate(type === "team" ? leftPayload.team : leftPayload.player, type), right: decorate(type === "team" ? rightPayload.team : rightPayload.player, type), compareRows: rowsFrom(leftPayload, rightPayload) });
  },

  changeLeft(event) {
    const leftIndex = Number(event.detail.value);
    this.loadComparison({ selectedScope: this.data.selectedScope, type: this.data.type, candidates: this.data.candidates, leftIndex, rightIndex: leftIndex === this.data.rightIndex ? (leftIndex === 0 ? 1 : 0) : this.data.rightIndex });
  },

  changeRight(event) {
    const rightIndex = Number(event.detail.value);
    this.loadComparison({ selectedScope: this.data.selectedScope, type: this.data.type, candidates: this.data.candidates, leftIndex: rightIndex === this.data.leftIndex ? (rightIndex === 0 ? 1 : 0) : this.data.leftIndex, rightIndex });
  },

  goCompetitions() { goCompetitions(); },

  openEntity(event) {
    const entity = event.currentTarget.dataset.side === "right" ? this.data.right : this.data.left;
    if (!entity) return;
    const page = this.data.type === "team" ? "team-detail" : "player-detail";
    const key = this.data.type === "team" ? "team_id" : "player_id";
    wx.navigateTo({ url: `/pages/${page}/${page}?${key}=${encodeURIComponent(entity.id)}` });
  },

  onImageError(event) { this.setData({ [`${event.currentTarget.dataset.side}.imageUrl`]: "" }); }
});
