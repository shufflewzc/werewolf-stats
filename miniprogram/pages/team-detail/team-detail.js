const { request, assetUrl } = require("../../utils/api");
const { take } = require("../../utils/format");
const { applyScopeFromOptions, getRequiredScope, goCompetitions, needsCompetitionState, scopeParams } = require("../../utils/scope");

function decorateMatch(item) {
  const isWin = item.result === "胜" || item.result === "win";
  const isLoss = item.result === "负" || item.result === "loss";
  const hasIdentityField = Object.prototype.hasOwnProperty.call(item || {}, "identity_summary")
    || Object.prototype.hasOwnProperty.call(item || {}, "role_summary");
  return {
    ...item,
    resultClass: isWin ? "is-win" : (isLoss ? "is-loss" : "is-neutral"),
    identitySummaryText: item.identity_summary || item.role_summary || (hasIdentityField ? "身份缺失" : "接口未更新")
  };
}

function decorateAchievement(item) {
  const tier = String((item && item.tier) || "locked");
  const labels = {
    legend: "传奇",
    gold: "金",
    silver: "银",
    bronze: "铜",
    locked: "待解锁"
  };
  return {
    ...item,
    tierLabel: labels[tier] || "标签",
    className: `tier-${tier}`
  };
}

Page({
  data: {
    loading: true,
    error: "",
    teamId: "",
    selectedScope: null,
    needsCompetition: false,
    team: {},
    metrics: [],
    insights: {},
    achievements: [],
    roster: [],
    matches: []
  },

  onLoad(options) {
    applyScopeFromOptions(options);
    this.setData({ teamId: decodeURIComponent(options.team_id || "") });
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData({ forceRefresh: true }).finally(() => wx.stopPullDownRefresh());
  },

  async loadData(options = {}) {
    const teamId = this.data.teamId;
    if (!teamId) {
      this.setData({ loading: false, error: "缺少战队 ID" });
      return;
    }

    this.setData({ loading: true, error: "" });
    try {
      const selectedScope = getRequiredScope();
      if (!selectedScope) {
        this.setData(needsCompetitionState({
          team: {},
          metrics: [],
          insights: {},
          achievements: [],
          roster: [],
          matches: []
        }));
        return;
      }
      const payload = await request(`/api/teams/${encodeURIComponent(teamId)}`, scopeParams(selectedScope), options);
      const team = payload.team || {};
      wx.setNavigationBarTitle({ title: team.short_name || team.name || "战队详情" });
      this.setData({
        loading: false,
        selectedScope,
        needsCompetition: false,
        team: {
          ...team,
          logoUrl: assetUrl(team.logo)
        },
        metrics: take(payload.metrics, 6),
        insights: payload.insights || {},
        achievements: take(payload.achievements, 12).map(decorateAchievement),
        roster: take(payload.roster, 12).map((player) => ({
          ...player,
          photoUrl: assetUrl(player.photo)
        })),
        matches: take(payload.matches, 8).map(decorateMatch)
      });
    } catch (error) {
      this.setData({
        loading: false,
        error: error.message || "战队详情加载失败"
      });
    }
  },

  changeCompetition() {
    goCompetitions();
  },

  goTeams() {
    wx.switchTab({ url: "/pages/guilds/guilds" });
  },

  goCompetitions() {
    goCompetitions();
  },

  openPlayer(event) {
    const playerId = event.currentTarget.dataset.playerId;
    if (!playerId) {
      return;
    }
    wx.navigateTo({ url: `/pages/player-detail/player-detail?player_id=${encodeURIComponent(playerId)}` });
  },

  onTeamImageError() {
    this.setData({ "team.logoUrl": "" });
  },

  onPlayerImageError(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (!Number.isFinite(index)) {
      return;
    }
    this.setData({ [`roster[${index}].photoUrl`]: "" });
  }
});
