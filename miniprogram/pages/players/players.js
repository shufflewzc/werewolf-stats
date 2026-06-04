const { request, assetUrl } = require("../../utils/api");
const { take } = require("../../utils/format");
const { getSelectedScope, scopeParams } = require("../../utils/scope");

Page({
  data: {
    loading: true,
    error: "",
    selectedScope: null,
    needsCompetition: false,
    requiresScope: false,
    scope: {},
    metrics: [],
    players: []
  },

  onShow() {
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData().finally(() => wx.stopPullDownRefresh());
  },

  async loadData() {
    this.setData({ loading: true, error: "" });
    try {
      const selectedScope = getSelectedScope();
      if (!selectedScope || !selectedScope.competition) {
        this.setData({
          loading: false,
          selectedScope: null,
          needsCompetition: true,
          requiresScope: false,
          scope: {},
          metrics: [],
          players: []
        });
        return;
      }

      let payload = await request("/api/players", scopeParams(selectedScope));
      if (payload.requires_scope) {
        const dashboard = await request("/api/dashboard", scopeParams(selectedScope));
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
      this.setData({
        loading: false,
        selectedScope,
        needsCompetition: false,
        requiresScope: Boolean(payload.requires_scope),
        scope: payload.scope || {},
        metrics: take(payload.metrics, 4),
        players: (payload.players || []).map((player) => ({
          ...player,
          photoUrl: assetUrl(player.photo)
        }))
      });
    } catch (error) {
      this.setData({
        loading: false,
        error: error.message || "选手数据加载失败"
      });
    }
  },

  goCompetitions() {
    wx.switchTab({ url: "/pages/competitions/competitions" });
  },

  openPlayerDetail(event) {
    const playerId = event.currentTarget.dataset.playerId;
    if (!playerId) {
      return;
    }
    wx.navigateTo({ url: `/pages/player-detail/player-detail?player_id=${encodeURIComponent(playerId)}` });
  }
});
