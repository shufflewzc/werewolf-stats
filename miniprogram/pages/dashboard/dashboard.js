const { request, assetUrl } = require("../../utils/api");
const { take } = require("../../utils/format");
const {
  buildScopeFromCompetition,
  clearSelectedScope,
  getSelectedScope,
  scopeParams,
  setSelectedScope
} = require("../../utils/scope");

Page({
  data: {
    loading: true,
    error: "",
    selectedScope: null,
    choosing: false,
    competitions: [],
    scopeLabel: "赛事数据中心",
    generatedAt: "",
    hero: {},
    metrics: [],
    topTeams: [],
    topPlayers: [],
    matchDays: []
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
        const competitions = await request("/api/competitions");
        this.setData({
          loading: false,
          choosing: true,
          selectedScope: null,
          scopeLabel: "选择赛事",
          generatedAt: competitions.generated_at || "",
          hero: competitions.hero || {},
          metrics: take(competitions.metrics, 4),
          competitions: competitions.cards || [],
          topTeams: [],
          topPlayers: [],
          matchDays: []
        });
        return;
      }

      const payload = await request("/api/dashboard", scopeParams(selectedScope));
      this.setData({
        loading: false,
        choosing: false,
        selectedScope,
        competitions: [],
        scopeLabel: (payload.scope && payload.scope.label) || "赛事数据中心",
        generatedAt: payload.generated_at || "",
        hero: payload.hero || {},
        metrics: take(payload.metrics, 4),
        topTeams: take(payload.top_teams, 5).map((team) => ({
          ...team,
          logoUrl: assetUrl(team.logo)
        })),
        topPlayers: take(payload.top_players, 5).map((player) => ({
          ...player,
          photoUrl: assetUrl(player.photo)
        })),
        matchDays: take(payload.match_days, 4)
      });
    } catch (error) {
      this.setData({
        loading: false,
        error: error.message || "首页数据加载失败"
      });
    }
  },

  goTeams() {
    wx.switchTab({ url: "/pages/guilds/guilds" });
  },

  goPlayers() {
    wx.switchTab({ url: "/pages/players/players" });
  },

  goPredictions() {
    wx.navigateTo({ url: "/pages/predictions/predictions" });
  },

  openPlayerDetail(event) {
    const playerId = event.currentTarget.dataset.playerId;
    if (!playerId) {
      return;
    }
    wx.navigateTo({ url: `/pages/player-detail/player-detail?player_id=${encodeURIComponent(playerId)}` });
  },

  chooseCompetition(event) {
    const index = Number(event.currentTarget.dataset.index);
    const card = this.data.competitions[index];
    const scope = buildScopeFromCompetition(card);
    setSelectedScope(scope);
    this.loadData();
  },

  changeCompetition() {
    clearSelectedScope();
    this.loadData();
  }
});
