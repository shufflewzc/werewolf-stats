const { request } = require("../../utils/api");
const { stageLabel } = require("../../utils/format");
const { createPagedState, nextPagedState } = require("../../utils/paging");
const { appendScopeToPath, applyScopeFromOptions, confirmScopeMismatch, getRequiredScope, goCompetitions, needsCompetitionState, sameScope, scopeActivationError, scopeParams } = require("../../utils/scope");

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
    const playedOn = decodeURIComponent(options.played_on || "");
    this.setData({ playedOn });
    this.activateScopeAndLoad(options);
  },

  async activateScopeAndLoad(options) {
    const activation = await applyScopeFromOptions(options, { sourceLabel: "分享的比赛日" });
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
    const scope = this.data.selectedScope;
    const playedOn = this.data.playedOn;
    return {
      title: `${scope && scope.competition ? scope.competition : "狼人杀赛事"} · ${playedOn || "比赛日"}赛程与日榜`,
      path: appendScopeToPath(`/pages/day-detail/day-detail?played_on=${encodeURIComponent(playedOn)}`, scope)
    };
  },

  async loadData(options = {}) {
    const requestId = Number(this._loadRequestId || 0) + 1;
    this._loadRequestId = requestId;
    this._predictionLoadMoreRequestId = Number(this._predictionLoadMoreRequestId || 0) + 1;
    this._predictionLoadMorePending = false;
    if (this._scopeEntryBlocked) {
      this.setData({ loading: false, error: this._scopeEntryBlocked });
      return;
    }
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
      if (
        requestId !== this._loadRequestId
        || !sameScope(getRequiredScope(), selectedScope)
        || this.data.playedOn !== playedOn
      ) {
        return;
      }
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
      if (requestId !== this._loadRequestId || !sameScope(getRequiredScope(), selectedScope)) {
        return;
      }
      const recovery = await confirmScopeMismatch(error, { sourceLabel: "该比赛日" });
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

  async loadMorePredictions() {
    const selectedScope = getRequiredScope();
    if (
      !selectedScope
      || !sameScope(selectedScope, this.data.selectedScope)
      || !this.data.predictionHasMore
      || this._predictionLoadMorePending
    ) {
      return false;
    }
    const requestId = Number(this._predictionLoadMoreRequestId || 0) + 1;
    const playedOn = this.data.playedOn;
    const offset = this.data.predictionVisibleCount;
    this._predictionLoadMoreRequestId = requestId;
    this._predictionLoadMorePending = true;
    try {
      const payload = await request("/api/predictions", {
        ...scopeParams(selectedScope),
        played_on: playedOn,
        limit: PAGE_SIZE,
        offset
      });
      if (
        requestId !== this._predictionLoadMoreRequestId
        || !sameScope(getRequiredScope(), selectedScope)
        || !sameScope(this.data.selectedScope, selectedScope)
        || this.data.playedOn !== playedOn
        || this.data.predictionVisibleCount !== offset
      ) {
        return false;
      }
      const predictions = this.data.predictions.concat(payload.predictions || []);
      const pagination = payload.pagination || {};
      this.setData({
        predictions,
        visiblePredictions: predictions,
        predictionVisibleCount: predictions.length,
        predictionTotalCount: Number(pagination.total || this.data.predictionTotalCount || predictions.length),
        predictionHasMore: Boolean(pagination.has_more)
      });
      return true;
    } catch (error) {
      if (requestId !== this._predictionLoadMoreRequestId || !sameScope(getRequiredScope(), selectedScope)) {
        return false;
      }
      this.setData({ error: error.message || "加载更多失败" });
      return false;
    } finally {
      if (requestId === this._predictionLoadMoreRequestId) {
        this._predictionLoadMorePending = false;
      }
    }
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
