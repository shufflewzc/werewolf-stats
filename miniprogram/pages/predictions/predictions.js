const { request } = require("../../utils/api");
const { getCurrentUser } = require("../../utils/auth");
const { getRequiredScope, goCompetitions, needsCompetitionState, scopeParams } = require("../../utils/scope");

const PAGE_SIZE = 30;

function predictionBand(score) {
  if (score >= 12) {
    return { label: "高分区", className: "band-elite" };
  }
  if (score >= 7) {
    return { label: "竞争区", className: "band-contender" };
  }
  if (score >= 5) {
    return { label: "主体区", className: "band-main" };
  }
  return { label: "观察区", className: "band-watch" };
}

function decoratePrediction(item, index, currentUser) {
  const expectedTotal = Number(item.expected_total || item.expected_points || 0);
  const band = predictionBand(expectedTotal);
  const rank = Number(item.rank || index + 1);
  return {
    ...item,
    expectedTotal,
    rank,
    rankText: `第 ${rank} 名`,
    bandLabel: band.label,
    bandClass: band.className,
    isMine: Boolean(currentUser && currentUser.player_id && item.player_id === currentUser.player_id),
    matchLabels: item.match_labels || []
  };
}

function summarizeBands(predictions) {
  return [
    { label: "12+", copy: "高分区", value: predictions.filter((item) => item.expectedTotal >= 12).length },
    { label: "7-12", copy: "竞争区", value: predictions.filter((item) => item.expectedTotal >= 7 && item.expectedTotal < 12).length },
    { label: "5-7", copy: "主体区", value: predictions.filter((item) => item.expectedTotal >= 5 && item.expectedTotal < 7).length }
  ];
}

Page({
  data: {
    loading: true,
    error: "",
    needsCompetition: false,
    selectedScope: null,
    scope: {},
    days: [],
    selectedDay: null,
    predictions: [],
    predictionTotalCount: 0,
    predictionVisibleCount: 0,
    predictionHasMore: false,
    bandSummary: [],
    currentUser: null,
    myPrediction: null,
    myPredictionText: "绑定选手后显示我的位置",
    notice: ""
  },

  onLoad(options) {
    this.initialPlayedOn = options.played_on || "";
    this.initialMatchId = options.match_id || "";
  },

  onShow() {
    this.loadData({
      playedOn: this.initialPlayedOn,
      matchId: this.initialMatchId
    });
    this.initialPlayedOn = "";
    this.initialMatchId = "";
  },

  onPullDownRefresh() {
    const playedOn = this.data.selectedDay && this.data.selectedDay.played_on;
    this.loadData({ playedOn: playedOn || "" }).finally(() => wx.stopPullDownRefresh());
  },

  async loadData(options = {}) {
    this.setData({ loading: true, error: "" });
    try {
      const selectedScope = getRequiredScope();
      if (!selectedScope) {
        this.setData(needsCompetitionState({
          scope: {},
          days: [],
          selectedDay: null,
          predictions: [],
          predictionTotalCount: 0,
          predictionVisibleCount: 0,
          predictionHasMore: false,
          bandSummary: [],
          currentUser: getCurrentUser(),
          myPrediction: null,
          myPredictionText: "绑定选手后显示我的位置",
          notice: ""
        }));
        return;
      }
      const currentUser = getCurrentUser();
      const paramsWithPaging = {
        ...scopeParams(selectedScope),
        played_on: options.playedOn || "",
        match_id: options.matchId || "",
        limit: PAGE_SIZE,
        offset: 0,
        focus_player_id: currentUser && currentUser.player_id ? currentUser.player_id : ""
      };
      const payload = await request("/api/predictions", paramsWithPaging);
      const predictions = (payload.predictions || []).map((item, index) => decoratePrediction(item, index, currentUser));
      const myPredictionSource = payload.focused_prediction || predictions.find((item) => item.isMine) || null;
      const myPrediction = myPredictionSource ? decoratePrediction(myPredictionSource, 0, currentUser) : null;
      const pagination = payload.pagination || {};
      this.setData({
        loading: false,
        needsCompetition: false,
        selectedScope,
        scope: payload.scope || {},
        days: payload.days || [],
        selectedDay: payload.selected_day || null,
        predictions,
        predictionTotalCount: Number(pagination.total || predictions.length),
        predictionVisibleCount: predictions.length,
        predictionHasMore: Boolean(pagination.has_more),
        bandSummary: payload.band_summary || summarizeBands(predictions),
        currentUser,
        myPrediction,
        myPredictionText: myPrediction
          ? `${myPrediction.rankText} · ${myPrediction.expected_total || myPrediction.expected_points} 分 · ${myPrediction.bandLabel}`
          : (currentUser && currentUser.player_id ? "当前比赛日没有我的预测" : "绑定选手后显示我的位置"),
        notice: payload.notice || ""
      });
    } catch (error) {
      this.setData({
        loading: false,
        error: error.message || "胜率预测加载失败"
      });
    }
  },

  chooseDay(event) {
    const playedOn = event.currentTarget.dataset.playedOn;
    if (!playedOn || (this.data.selectedDay && this.data.selectedDay.played_on === playedOn)) {
      return;
    }
    this.loadData({ playedOn });
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
    const selectedDay = this.data.selectedDay || {};
    if (!selectedScope || !this.data.predictionHasMore) {
      return;
    }
    const currentUser = getCurrentUser();
    request("/api/predictions", {
      ...scopeParams(selectedScope),
      played_on: selectedDay.played_on || "",
      limit: PAGE_SIZE,
      offset: this.data.predictionVisibleCount,
      focus_player_id: currentUser && currentUser.player_id ? currentUser.player_id : ""
    }).then((payload) => {
      const morePredictions = (payload.predictions || []).map((item, index) => (
        decoratePrediction(item, this.data.predictionVisibleCount + index, currentUser)
      ));
      const predictions = this.data.predictions.concat(morePredictions);
      const pagination = payload.pagination || {};
      this.setData({
        predictions,
        predictionVisibleCount: predictions.length,
        predictionTotalCount: Number(pagination.total || this.data.predictionTotalCount || predictions.length),
        predictionHasMore: Boolean(pagination.has_more)
      });
    }).catch((error) => {
      this.setData({ error: error.message || "加载更多失败" });
    });
  },

  goCompetitions() {
    goCompetitions();
  },

  changeCompetition() {
    goCompetitions();
  }
});
