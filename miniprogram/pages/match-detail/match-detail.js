const { request } = require("../../utils/api");
const { compactText, stageLabel } = require("../../utils/format");
const { appendScopeToPath, applyScopeFromOptions, confirmScopeMismatch, getRequiredScope, goCompetitions, needsCompetitionState, scopeActivationError, scopeParams } = require("../../utils/scope");

function decorateBadges(item) {
  const groupLabel = item.group_label || item.regular_season_group || "";
  const fallback = groupLabel
    ? [{
      text: groupLabel,
      style: String(groupLabel).indexOf("S") === 0 ? "gold" : "blue",
      kind: "group"
    }]
    : [];
  return (Array.isArray(item.badges) && item.badges.length ? item.badges : fallback)
    .map((badge) => ({
      ...badge,
      className: `is-${badge.style || "gray"}`
    }));
}

function decorateParticipant(item) {
  const breakdown = item.breakdown || {};
  const result = String(item.result || "");
  return {
    ...item,
    resultClass: result === "胜" ? "is-win" : (result === "负" ? "is-loss" : ""),
    groupClass: String(item.regular_season_group || "").indexOf("S") === 0 ? "is-s" : "is-f",
    badges: decorateBadges(item),
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
    needsCompetition: false,
    match: {},
    metrics: [],
    awards: [],
    teamScores: [],
    participants: [],
    scoreFields: [],
    groupLabels: [],
    groupLabelsText: ""
  },

  onLoad(options) {
    this.setData({
      matchId: decodeURIComponent(options.match_id || "")
    });
    this.activateScopeAndLoad(options);
  },

  async activateScopeAndLoad(options) {
    const activation = await applyScopeFromOptions(options, { sourceLabel: "分享的比赛详情" });
    if (!activation.accepted) {
      this._scopeEntryBlocked = scopeActivationError(activation);
      this.setData({ loading: false, error: this._scopeEntryBlocked });
      return;
    }
    this._scopeEntryBlocked = "";
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData({ forceRefresh: true }).finally(() => wx.stopPullDownRefresh());
  },

  onShareAppMessage() {
    const match = this.data.match || {};
    return {
      title: compactText([
        match.competition || "狼人杀赛事",
        stageLabel(match, ""),
        `第${match.round || "--"}轮第${match.game_no || "--"}局`
      ]),
      path: appendScopeToPath(
        `/pages/match-detail/match-detail?match_id=${encodeURIComponent(this.data.matchId)}`,
        this.data.selectedScope
      )
    };
  },

  async loadData(options = {}) {
    if (this._scopeEntryBlocked) {
      this.setData({ loading: false, error: this._scopeEntryBlocked });
      return;
    }
    const matchId = this.data.matchId;
    if (!matchId) {
      this.setData({ loading: false, error: "缺少比赛 ID" });
      return;
    }
    this.setData({ loading: true, error: "" });
    try {
      const selectedScope = getRequiredScope();
      if (!selectedScope) {
        this.setData(needsCompetitionState({
          match: {},
          metrics: [],
          awards: [],
          teamScores: [],
          participants: [],
          scoreFields: [],
          groupLabels: [],
          groupLabelsText: ""
        }));
        return;
      }
      const payload = await request(
        `/api/matches/${encodeURIComponent(matchId)}`,
        scopeParams(selectedScope),
        options
      );
      if (payload.not_found) {
        this.setData({ loading: false, error: payload.error || "没有找到对应的比赛" });
        return;
      }
      const rawMatch = payload.match || {};
      const match = {
        ...rawMatch,
        stage_label: stageLabel(rawMatch, "赛程")
      };
      wx.setNavigationBarTitle({
        title: match.played_on ? `${match.played_on} 比赛` : "比赛详情"
      });
      this.setData({
        loading: false,
        selectedScope,
        needsCompetition: false,
        match,
        metrics: payload.metrics || [],
        awards: (payload.awards || []).map((item) => ({
          ...item,
          available: Boolean(item.player_id)
        })),
        teamScores: (payload.team_scores || []).map((item) => ({
          ...item,
          groupClass: String(item.regular_season_group || "").indexOf("S") === 0 ? "is-s" : "is-f",
          badges: decorateBadges(item)
        })),
        participants: (payload.participants || []).map(decorateParticipant),
        scoreFields: payload.score_fields || [],
        groupLabels: match.group_labels || [],
        groupLabelsText: (match.group_labels || []).join(" / ")
      });
    } catch (error) {
      const recovery = await confirmScopeMismatch(error, { sourceLabel: "该场比赛" });
      if (recovery) {
        if (recovery.accepted && !options.scopeMismatchRetried) {
          return this.loadData({ ...options, forceRefresh: true, scopeMismatchRetried: true });
        }
        if (!recovery.accepted) {
          this.setData({ loading: false, error: scopeActivationError(recovery) });
          return;
        }
      }
      this.setData({
        loading: false,
        error: error.message || "比赛详情加载失败"
      });
    }
  },

  goCompetitions() {
    goCompetitions();
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
