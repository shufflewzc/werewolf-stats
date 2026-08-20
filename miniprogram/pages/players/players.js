const { request, assetUrl } = require("../../utils/api");
const { take } = require("../../utils/format");
const { appendScopeToPath, applyScopeFromOptions, confirmScopeMismatch, getRequiredScope, goCompetitions, needsCompetitionState, sameScope, scopeActivationError, scopeParams } = require("../../utils/scope");

const PAGE_SIZE = 30;

Page({
  data: {
    loading: true,
    error: "",
    selectedScope: null,
    needsCompetition: false,
    scope: {},
    metrics: [],
    players: [],
    visiblePlayers: [],
    playerTotalCount: 0,
    playerVisibleCount: 0,
    playerHasMore: false,
    loadingMore: false,
    loadMoreError: ""
  },

  onLoad(options) {
    this._scopeReady = applyScopeFromOptions(options, { sourceLabel: "分享的选手列表" });
  },

  async onShow() {
    if (this._scopeReady) {
      const activation = await this._scopeReady;
      this._scopeReady = null;
      if (!activation.accepted) {
        this._scopeEntryBlocked = scopeActivationError(activation);
        this.setData({ loading: false, error: this._scopeEntryBlocked });
        return false;
      }
    } else {
      this._scopeEntryBlocked = "";
    }
    return this.loadData();
  },

  onPullDownRefresh() {
    this.loadData({ forceRefresh: true }).finally(() => wx.stopPullDownRefresh());
  },

  onShareAppMessage() {
    const scope = this.data.selectedScope;
    return {
      title: `${scope && scope.competition ? scope.competition : "狼人杀赛事"} · ${scope && scope.season ? scope.season : "选手榜"}`,
      path: appendScopeToPath("/pages/players/players", scope)
    };
  },

  async loadData(options = {}) {
    if (this._scopeEntryBlocked) {
      this.setData({ loading: false, error: this._scopeEntryBlocked });
      return false;
    }
    const requestId = Number(this._loadRequestId || 0) + 1;
    this._loadRequestId = requestId;
    this._loadMoreRequestId = Number(this._loadMoreRequestId || 0) + 1;
    this.setData({ loading: true, error: "", loadingMore: false, loadMoreError: "" });
    const selectedScope = getRequiredScope();
    try {
      if (!selectedScope) {
        this.setData(needsCompetitionState({
          scope: {},
          metrics: [],
          players: [],
          visiblePlayers: [],
          playerTotalCount: 0,
          playerVisibleCount: 0,
          playerHasMore: false
        }));
        return;
      }

      const payload = await request("/api/players", {
        ...scopeParams(selectedScope),
        limit: PAGE_SIZE,
        offset: 0
      }, options);
      if (requestId !== this._loadRequestId || !sameScope(getRequiredScope(), selectedScope)) {
        return;
      }
      const players = (payload.players || []).map((player) => ({
        ...player,
        photoUrl: assetUrl(player.photo)
      }));
      const pagination = payload.pagination || {};
      this.setData({
        loading: false,
        selectedScope,
        needsCompetition: false,
        scope: payload.scope || {},
        metrics: take(payload.metrics, 4),
        players,
        visiblePlayers: players,
        playerTotalCount: Number(pagination.total || players.length),
        playerVisibleCount: players.length,
        playerHasMore: Boolean(pagination.has_more),
        loadingMore: false,
        loadMoreError: ""
      });
    } catch (error) {
      if (requestId !== this._loadRequestId || !sameScope(getRequiredScope(), selectedScope)) {
        return;
      }
      const recovery = await confirmScopeMismatch(error, { sourceLabel: "该选手列表" });
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
        error: error.message || "选手数据加载失败"
      });
    }
  },

  goCompetitions() {
    goCompetitions();
  },

  changeCompetition() {
    goCompetitions();
  },

  openPlayerDetail(event) {
    const playerId = event.currentTarget.dataset.playerId;
    if (!playerId) {
      return;
    }
    wx.navigateTo({ url: `/pages/player-detail/player-detail?player_id=${encodeURIComponent(playerId)}` });
  },

  onPlayerImageError(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (!Number.isFinite(index)) {
      return;
    }
    this.setData({
      [`players[${index}].photoUrl`]: "",
      [`visiblePlayers[${index}].photoUrl`]: ""
    });
  },

  async loadMorePlayers() {
    const selectedScope = getRequiredScope();
    if (!selectedScope || !sameScope(selectedScope, this.data.selectedScope) || !this.data.playerHasMore || this.data.loadingMore) {
      return false;
    }
    const requestId = Number(this._loadMoreRequestId || 0) + 1;
    const offset = this.data.playerVisibleCount;
    this._loadMoreRequestId = requestId;
    this.setData({ loadingMore: true, loadMoreError: "" });
    try {
      const payload = await request("/api/players", {
        ...scopeParams(selectedScope),
        limit: PAGE_SIZE,
        offset
      });
      if (
        requestId !== this._loadMoreRequestId
        || !sameScope(getRequiredScope(), selectedScope)
        || !sameScope(this.data.selectedScope, selectedScope)
        || this.data.playerVisibleCount !== offset
      ) {
        if (requestId === this._loadMoreRequestId) {
          this.setData({ loadingMore: false });
        }
        return false;
      }
      const morePlayers = (payload.players || []).map((player) => ({
        ...player,
        photoUrl: assetUrl(player.photo)
      }));
      const players = this.data.players.concat(morePlayers);
      const pagination = payload.pagination || {};
      this.setData({
        players,
        visiblePlayers: players,
        playerVisibleCount: players.length,
        playerTotalCount: Number(pagination.total || this.data.playerTotalCount || players.length),
        playerHasMore: Boolean(pagination.has_more),
        loadingMore: false,
        loadMoreError: ""
      });
      return true;
    } catch (error) {
      if (requestId !== this._loadMoreRequestId) {
        return false;
      }
      if (!sameScope(getRequiredScope(), selectedScope)) {
        this.setData({ loadingMore: false });
        return false;
      }
      this.setData({ loadingMore: false, loadMoreError: error.message || "加载更多失败" });
      return false;
    }
  }
});
