const { request } = require("../../utils/api");
const { stageLabel } = require("../../utils/format");
const { createPagedState, nextPagedState } = require("../../utils/paging");
const { appendScopeToPath, applyScopeFromOptions, getRequiredScope, goCompetitions, needsCompetitionState, scopeParams } = require("../../utils/scope");

const PAGE_SIZE = 30;

function decorateCompetition(item) {
  return {
    ...item,
    matches: (item.matches || []).map((match) => ({
      ...match,
      stage_label: stageLabel(match, "赛段未设置")
    }))
  };
}

Page({
  data: {
    loading: true,
    error: "",
    needsCompetition: false,
    playedOn: "",
    selectedScope: null,
    hero: {},
    metrics: [],
    heroSide: {},
    teamLeaderboard: [],
    playerLeaderboard: [],
    visiblePlayerLeaderboard: [],
    playerTotalCount: 0,
    playerVisibleCount: 0,
    playerHasMore: false,
    competitions: [],
    predictions: [],
    visiblePredictions: [],
    predictionTotalCount: 0,
    predictionVisibleCount: 0,
    predictionHasMore: false
  },

  onLoad(options) {
    applyScopeFromOptions(options);
    const playedOn = decodeURIComponent(options.played_on || "");
    this.setData({ playedOn });
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData({ forceRefresh: true }).finally(() => wx.stopPullDownRefresh());
  },

  onShareAppMessage() {
    const scope = this.data.selectedScope;
    const playedOn = this.data.playedOn;
    return {
      title: `${scope && scope.competition ? scope.competition : "狼人杀赛事"} · ${playedOn || "比赛日"}赛程与日榜`,
      path: appendScopeToPath(`/pages/day-detail/day-detail?played_on=${encodeURIComponent(playedOn)}`, scope)
    };
  },

  async loadData(options = {}) {
    const playedOn = this.data.playedOn;
    if (!playedOn) {
      this.setData({ loading: false, error: "缺少比赛日期" });
      return;
    }
    const selectedScope = getRequiredScope();
    if (!selectedScope) {
      this.setData(needsCompetitionState({
        hero: {},
        metrics: [],
        heroSide: {},
        teamLeaderboard: [],
        playerLeaderboard: [],
        visiblePlayerLeaderboard: [],
        playerTotalCount: 0,
        playerVisibleCount: 0,
        playerHasMore: false,
        competitions: [],
        predictions: [],
        visiblePredictions: [],
        predictionTotalCount: 0,
        predictionVisibleCount: 0,
        predictionHasMore: false
      }));
      return;
    }
    this.setData({ loading: true, error: "" });
    try {
      const params = scopeParams(selectedScope);
      const [dayPayload, predictionPayload] = await Promise.all([
        request(`/api/days/${encodeURIComponent(playedOn)}`, params, options),
        request("/api/predictions", {
          ...params,
          played_on: playedOn,
          limit: PAGE_SIZE,
          offset: 0
        }, options)
      ]);
      const predictions = predictionPayload.predictions || [];
      const playerLeaderboard = dayPayload.player_leaderboard || [];
      const predictionPagination = predictionPayload.pagination || {};
      const pagedPlayers = createPagedState(playerLeaderboard);
      wx.setNavigationBarTitle({ title: `${playedOn} 比赛日` });
      this.setData({
        loading: false,
        needsCompetition: false,
        selectedScope,
        hero: dayPayload.hero || {},
        metrics: dayPayload.metrics || [],
        heroSide: dayPayload.hero_side || {},
        teamLeaderboard: (dayPayload.team_leaderboard || []).slice(0, 8),
        playerLeaderboard,
        visiblePlayerLeaderboard: pagedPlayers.visibleItems,
        playerTotalCount: pagedPlayers.totalCount,
        playerVisibleCount: pagedPlayers.visibleCount,
        playerHasMore: pagedPlayers.hasMore,
        competitions: (dayPayload.competitions || []).map(decorateCompetition),
        predictions,
        visiblePredictions: predictions,
        predictionTotalCount: Number(predictionPagination.total || predictions.length),
        predictionVisibleCount: predictions.length,
        predictionHasMore: Boolean(predictionPagination.has_more)
      });
    } catch (error) {
      this.setData({
        loading: false,
        error: error.message || "比赛日详情加载失败"
      });
    }
  },

  goPredictions() {
    const playedOn = this.data.playedOn;
    wx.navigateTo({ url: `/pages/predictions/predictions?played_on=${encodeURIComponent(playedOn)}` });
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

  loadMorePredictions() {
    const selectedScope = getRequiredScope();
    if (!selectedScope || !this.data.predictionHasMore) {
      return;
    }
    request("/api/predictions", {
      ...scopeParams(selectedScope),
      played_on: this.data.playedOn,
      limit: PAGE_SIZE,
      offset: this.data.predictionVisibleCount
    }).then((payload) => {
      const predictions = this.data.predictions.concat(payload.predictions || []);
      const pagination = payload.pagination || {};
      this.setData({
        predictions,
        visiblePredictions: predictions,
        predictionVisibleCount: predictions.length,
        predictionTotalCount: Number(pagination.total || this.data.predictionTotalCount || predictions.length),
        predictionHasMore: Boolean(pagination.has_more)
      });
    }).catch((error) => {
      this.setData({ error: error.message || "加载更多失败" });
    });
  },

  loadMorePlayers() {
    const pagedPlayers = nextPagedState({
      allItems: this.data.playerLeaderboard,
      pageSize: 30,
      visibleCount: this.data.playerVisibleCount
    });
    this.setData({
      visiblePlayerLeaderboard: pagedPlayers.visibleItems,
      playerVisibleCount: pagedPlayers.visibleCount,
      playerHasMore: pagedPlayers.hasMore
    });
  }
});
