const { request, assetUrl } = require("../../utils/api");
const { getCurrentUser } = require("../../utils/auth");
const { take } = require("../../utils/format");
const {
  buildScopeFromCompetition,
  clearSelectedScope,
  getSelectedScope,
  scopeParams,
  setSelectedScope
} = require("../../utils/scope");

function predictionBand(score) {
  if (score >= 12) {
    return "高分区";
  }
  if (score >= 7) {
    return "竞争区";
  }
  if (score >= 5) {
    return "主体区";
  }
  return "观察区";
}

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
    matchDays: [],
    latestDay: null,
    currentUser: null,
    myPlayer: null,
    myPrediction: null,
    myPredictionValue: "--",
    myPredictionRank: "",
    myPredictionBand: "",
    myEmptyText: "微信登录后，可以绑定选手并查看自己的赛事数据。",
    myPrimaryActionText: "去登录",
    myStatusLabel: "未登录"
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
      const topPlayers = take(payload.top_players, 5).map((player) => ({
        ...player,
        photoUrl: assetUrl(player.photo)
      }));
      const matchDays = take(payload.match_days, 4);
      const latestDay = matchDays[0] || null;
      const currentUser = getCurrentUser();
      let myPlayer = null;
      let myPrediction = null;
      let myPredictionValue = "--";
      let myPredictionRank = "";
      let myPredictionBand = "";
      let myEmptyText = "微信登录后，可以绑定选手并查看自己的赛事数据。";
      let myPrimaryActionText = "去登录";
      let myStatusLabel = "未登录";
      if (currentUser && currentUser.player_id) {
        myStatusLabel = "已绑定选手";
        myPrimaryActionText = "我的选手页";
        myPlayer = topPlayers.find((player) => player.player_id === currentUser.player_id) || {
          player_id: currentUser.player_id,
          display_name: currentUser.display_name || currentUser.player_id,
          team_name: "进入详情查看",
          points_total: "--",
          games_played: "--",
          photoUrl: ""
        };
        if (latestDay && latestDay.played_on) {
          try {
            const predictionPayload = await request("/api/predictions", {
              ...scopeParams(selectedScope),
              played_on: latestDay.played_on
            });
            const predictions = predictionPayload.predictions || [];
            const predictionIndex = predictions.findIndex((item) => item.player_id === currentUser.player_id);
            myPrediction = predictionIndex >= 0 ? predictions[predictionIndex] : null;
            myPredictionValue = myPrediction ? (myPrediction.expected_total || myPrediction.expected_points || "--") : "--";
            if (myPrediction) {
              myPredictionRank = `第 ${predictionIndex + 1} 名`;
              myPredictionBand = predictionBand(Number(myPrediction.expected_total || myPrediction.expected_points || 0));
            }
          } catch (predictionError) {
            myPrediction = null;
          }
        }
      } else if (currentUser) {
        myStatusLabel = "未绑定选手";
        myEmptyText = "绑定选手后，这里会显示你的赛事入口和当日预测。";
        myPrimaryActionText = "绑定选手";
      }
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
        topPlayers,
        matchDays,
        latestDay,
        currentUser,
        myPlayer,
        myPrediction,
        myPredictionValue,
        myPredictionRank,
        myPredictionBand,
        myEmptyText,
        myPrimaryActionText,
        myStatusLabel
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

  openLatestDayPrediction(event) {
    const playedOn = event && event.currentTarget ? event.currentTarget.dataset.playedOn : "";
    const latestDay = this.data.latestDay;
    const targetDay = playedOn || (latestDay && latestDay.played_on) || "";
    if (targetDay) {
      wx.navigateTo({ url: `/pages/predictions/predictions?played_on=${encodeURIComponent(targetDay)}` });
      return;
    }
    wx.navigateTo({ url: "/pages/predictions/predictions" });
  },

  openDayDetail(event) {
    const playedOn = event && event.currentTarget ? event.currentTarget.dataset.playedOn : "";
    const latestDay = this.data.latestDay;
    const targetDay = playedOn || (latestDay && latestDay.played_on) || "";
    if (!targetDay) {
      return;
    }
    wx.navigateTo({ url: `/pages/day-detail/day-detail?played_on=${encodeURIComponent(targetDay)}` });
  },

  goMine() {
    wx.switchTab({ url: "/pages/mine/mine" });
  },

  goBindPlayer() {
    const currentUser = this.data.currentUser;
    if (!currentUser) {
      wx.switchTab({ url: "/pages/mine/mine" });
      return;
    }
    wx.navigateTo({ url: "/pages/player-bind/player-bind" });
  },

  openMyPlayerDetail() {
    const myPlayer = this.data.myPlayer;
    if (!myPlayer || !myPlayer.player_id) {
      this.goBindPlayer();
      return;
    }
    wx.navigateTo({ url: `/pages/player-detail/player-detail?player_id=${encodeURIComponent(myPlayer.player_id)}` });
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
