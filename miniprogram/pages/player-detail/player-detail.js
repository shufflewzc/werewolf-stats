const { request, assetUrl } = require("../../utils/api");
const { take } = require("../../utils/format");
const { getRequiredScope, goCompetitions, needsCompetitionState, scopeParams } = require("../../utils/scope");

function parsePercent(value) {
  const number = Number(String(value || "").replace("%", ""));
  return Number.isFinite(number) ? number : 0;
}

function buildSummaryCards(payload, normalizedDimension) {
  const insights = payload.insights || {};
  const recentMatches = payload.recent_matches || [];
  const dimensionRadar = normalizedDimension.radar || [];
  const villagersRate = parsePercent(insights.villagers_win_rate);
  const werewolvesRate = parsePercent(insights.werewolves_win_rate);
  const strongerCamp = werewolvesRate >= villagersRate ? "狼人局" : "好人局";
  const strongerRate = werewolvesRate >= villagersRate ? insights.werewolves_win_rate : insights.villagers_win_rate;
  const recentWins = recentMatches.filter((item) => item.result_label === "胜" || item.result === "win").length;
  const recentPoints = recentMatches.reduce((sum, item) => sum + Number(item.points_earned || 0), 0);
  const bestDimension = dimensionRadar.reduce((best, item) => {
    if (!best || Number(item.ratio || 0) > Number(best.ratio || 0)) {
      return item;
    }
    return best;
  }, null);
  return [
    {
      label: "强势阵营",
      value: strongerRate || "--",
      copy: strongerCamp
    },
    {
      label: "近期走势",
      value: recentMatches.length ? `${recentWins}/${recentMatches.length}` : "--",
      copy: recentMatches.length ? `近${recentMatches.length}局 ${recentPoints.toFixed(1)}分` : "暂无近期比赛"
    },
    {
      label: "维度强项",
      value: bestDimension ? bestDimension.display : "--",
      copy: bestDimension ? bestDimension.label : "暂无维度数据"
    }
  ];
}

function decorateRecentMatch(item) {
  const result = String((item && (item.result_label || item.result)) || "");
  const isWin = result === "胜" || result === "win";
  const isLoss = result === "负" || result === "loss";
  return {
    ...item,
    resultClass: isWin ? "is-win" : (isLoss ? "is-loss" : "is-neutral"),
    resultText: item.result_label || (isWin ? "胜" : (isLoss ? "负" : item.result || "--"))
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
    playerId: "",
    selectedScope: null,
    needsCompetition: false,
    player: {},
    metrics: [],
    insights: {},
    summaryCards: [],
    roles: [],
    recentMatches: [],
    achievements: [],
    dimension: {},
    dimensionAvailable: false
  },

  onLoad(options) {
    this.setData({ playerId: decodeURIComponent(options.player_id || "") });
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData().finally(() => wx.stopPullDownRefresh());
  },

  async loadData() {
    const playerId = this.data.playerId;
    if (!playerId) {
      this.setData({ loading: false, error: "缺少选手 ID" });
      return;
    }

    this.setData({ loading: true, error: "" });
    try {
      const selectedScope = getRequiredScope();
      if (!selectedScope) {
        this.setData(needsCompetitionState({
          player: {},
          metrics: [],
          insights: {},
          summaryCards: [],
          roles: [],
          recentMatches: [],
          achievements: [],
          dimension: {},
          dimensionAvailable: false
        }));
        return;
      }
      const payload = await request(`/api/players/${encodeURIComponent(playerId)}`, scopeParams(selectedScope));
      const player = payload.player || {};
      const dimension = payload.dimension || {};
      const normalizedDimension = {
        ...dimension,
        radar: (dimension.radar || []).map((item) => ({
          ...item,
          width: Math.max(0, Math.min(100, Number(item.ratio || 0) * 100))
        }))
      };
      const summaryCards = buildSummaryCards(payload, normalizedDimension);
      wx.setNavigationBarTitle({ title: player.name || "选手详情" });
      this.setData({
        loading: false,
        selectedScope,
        needsCompetition: false,
        player: {
          ...player,
          photoUrl: assetUrl(player.photo)
        },
        metrics: take(payload.metrics, 6),
        insights: payload.insights || {},
        summaryCards,
        roles: take(payload.roles, 8),
        recentMatches: take(payload.recent_matches, 6).map(decorateRecentMatch),
        achievements: take(payload.achievements, 12).map(decorateAchievement),
        dimension: normalizedDimension,
        dimensionAvailable: Boolean(normalizedDimension.available)
      });
    } catch (error) {
      this.setData({
        loading: false,
        error: error.message || "选手详情加载失败"
      });
    }
  },

  goPlayers() {
    wx.switchTab({ url: "/pages/players/players" });
  },

  goPredictions() {
    wx.navigateTo({ url: "/pages/predictions/predictions" });
  },

  changeCompetition() {
    goCompetitions();
  },

  onPlayerImageError() {
    this.setData({ "player.photoUrl": "" });
  },

  goCompetitions() {
    goCompetitions();
  }
});
