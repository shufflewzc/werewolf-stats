const { request, assetUrl } = require("../../utils/api");
const { take } = require("../../utils/format");
const { getRequiredScope, goCompetitions, needsCompetitionState, scopeParams } = require("../../utils/scope");

const PAGE_SIZE = 30;

Page({
  data: {
    loading: true,
    error: "",
    selectedScope: null,
    needsCompetition: false,
    requiresScope: false,
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

  onShow() {
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
        this.setData(needsCompetitionState({
          requiresScope: false,
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

      let payload = await request("/api/players", {
        ...scopeParams(selectedScope),
        limit: PAGE_SIZE,
        offset: 0
      }, options);
      if (payload.requires_scope) {
        const dashboard = await request("/api/dashboard", scopeParams(selectedScope), options);
        payload = {
          generated_at: dashboard.generated_at,
          scope: dashboard.scope || {},
          metrics: [
            { label: "榜单选手", value: String((dashboard.top_players || []).length), copy: "首页聚合接口返回的选手榜。" },
            { label: "当前范围", value: (dashboard.scope && dashboard.scope.dashboard_label) || "赛事", copy: "跟随网站首页的默认展示范围。" }
          ],
          players: dashboard.top_players || []
        };
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
        requiresScope: Boolean(payload.requires_scope),
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

  loadMorePlayers() {
    const selectedScope = getRequiredScope();
    if (!selectedScope || !this.data.playerHasMore || this.data.loadingMore) {
      return;
    }
    this.setData({ loadingMore: true, loadMoreError: "" });
    request("/api/players", {
      ...scopeParams(selectedScope),
      limit: PAGE_SIZE,
      offset: this.data.playerVisibleCount
    }).then((payload) => {
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
    }).catch((error) => {
      this.setData({ loadingMore: false, loadMoreError: error.message || "加载更多失败" });
    });
  }
});
