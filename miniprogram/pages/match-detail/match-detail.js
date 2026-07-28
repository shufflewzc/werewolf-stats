const { request } = require("../../utils/api");
const { appendScopeToPath, applyScopeFromOptions, getRequiredScope, scopeParams } = require("../../utils/scope");

function decorateParticipant(item) {
  const breakdown = item.breakdown || {};
  const result = String(item.result || "");
  return {
    ...item,
    resultClass: result === "胜" ? "is-win" : (result === "负" ? "is-loss" : ""),
    breakdownEntries: Object.keys(breakdown).map((label) => ({
      label,
      value: breakdown[label]
    }))
  };
}

Page({
  data: {
    loading: true,
    error: "",
    matchId: "",
    selectedScope: null,
    match: {},
    metrics: [],
    awards: [],
    teamScores: [],
    participants: [],
    scoreFields: []
  },

  onLoad(options) {
    applyScopeFromOptions(options);
    this.setData({
      matchId: decodeURIComponent(options.match_id || ""),
      selectedScope: getRequiredScope()
    });
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData({ forceRefresh: true }).finally(() => wx.stopPullDownRefresh());
  },

  onShareAppMessage() {
    const match = this.data.match || {};
    return {
      title: `${match.competition || "狼人杀赛事"} · 第${match.round || "--"}轮第${match.game_no || "--"}局`,
      path: appendScopeToPath(
        `/pages/match-detail/match-detail?match_id=${encodeURIComponent(this.data.matchId)}`,
        this.data.selectedScope
      )
    };
  },

  async loadData(options = {}) {
    const matchId = this.data.matchId;
    if (!matchId) {
      this.setData({ loading: false, error: "缺少比赛 ID" });
      return;
    }
    this.setData({ loading: true, error: "" });
    try {
      const selectedScope = getRequiredScope();
      const payload = await request(
        `/api/matches/${encodeURIComponent(matchId)}`,
        scopeParams(selectedScope),
        options
      );
      if (payload.not_found) {
        this.setData({ loading: false, error: payload.error || "没有找到对应的比赛" });
        return;
      }
      const match = payload.match || {};
      wx.setNavigationBarTitle({
        title: match.played_on ? `${match.played_on} 比赛` : "比赛详情"
      });
      this.setData({
        loading: false,
        selectedScope,
        match,
        metrics: payload.metrics || [],
        awards: (payload.awards || []).map((item) => ({
          ...item,
          available: Boolean(item.player_id)
        })),
        teamScores: payload.team_scores || [],
        participants: (payload.participants || []).map(decorateParticipant),
        scoreFields: payload.score_fields || []
      });
    } catch (error) {
      this.setData({
        loading: false,
        error: error.message || "比赛详情加载失败"
      });
    }
  },

  openPlayer(event) {
    const playerId = event.currentTarget.dataset.playerId;
    if (!playerId) {
      return;
    }
    wx.navigateTo({
      url: appendScopeToPath(
        `/pages/player-detail/player-detail?player_id=${encodeURIComponent(playerId)}&strict_player_id=1`,
        this.data.selectedScope
      )
    });
  },

  openTeam(event) {
    const teamId = event.currentTarget.dataset.teamId;
    if (!teamId) {
      return;
    }
    wx.navigateTo({
      url: appendScopeToPath(
        `/pages/team-detail/team-detail?team_id=${encodeURIComponent(teamId)}`,
        this.data.selectedScope
      )
    });
  }
});
