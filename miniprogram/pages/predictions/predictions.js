const { request } = require("../../utils/api");
const { appendScopeToPath, applyScopeFromOptions, getRequiredScope, goCompetitions, needsCompetitionState, scopeParams } = require("../../utils/scope");

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

function decoratePrediction(item, index) {
  const expectedTotal = Number(item.expected_total || item.expected_points || 0);
  const band = predictionBand(expectedTotal);
  const rank = Number(item.rank || index + 1);
  const gameWinDisplays = item.game_win_displays || (item.game_win_probabilities || []).map((value) => `${(Number(value) * 100).toFixed(1)}%`);
  const expectedWinsText = item.expected_wins === null || item.expected_wins === undefined ? "--" : Number(item.expected_wins).toFixed(2);
  return {
    ...item,
    expectedTotal,
    rank,
    rankText: `第 ${rank} 名`,
    bandLabel: band.label,
    bandClass: band.className,
    matchLabels: item.match_labels || [],
    profilePlayerId: item.profile_href ? item.player_id : "",
    gameWinDisplays,
    hasThreeGame: gameWinDisplays.length === 3,
    expectedWinsText,
    predictionMeta: gameWinDisplays.length === 3
      ? `${item.team_name || "未绑定战队"} · 预计 ${expectedWinsText} 胜 · 置信度 ${item.confidence || "--"}`
      : `${item.team_name || "未绑定战队"} · 当日 ${item.match_count || 0} 场 · 场均 ${item.average_expected_points || "--"}`,
    winCountLabels: (item.win_count_probabilities || []).map((entry) => `${entry.wins}胜 ${entry.display || `${(Number(entry.probability || 0) * 100).toFixed(1)}%`}`),
    winCountText: (item.win_count_probabilities || []).map((entry) => `${entry.wins}胜 ${entry.display || `${(Number(entry.probability || 0) * 100).toFixed(1)}%`}`).join(" · "),
    markets: (item.market_probabilities || []).map((market) => ({
      ...market,
      equalityDisplay: market.equality_display || `${(Number(market.equality_probability || 0) * 100).toFixed(1)}%`
    }))
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
    loadingMore: false,
    loadMoreError: "",
    bandSummary: [],
    notice: "",
    rosterSource: "none",
    modelMetadata: {},
    scenario: null,
    canGeneratePredictionCard: false
  },

  onLoad(options) {
    applyScopeFromOptions(options);
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
    this.loadData({ playedOn: playedOn || "", forceRefresh: true }).finally(() => wx.stopPullDownRefresh());
  },

  onShareAppMessage() {
    const scope = this.data.selectedScope;
    const selectedDay = this.data.selectedDay || {};
    return {
      title: `${scope && scope.competition ? scope.competition : "狼人杀赛事"} · ${selectedDay.played_on || "当天"}预测`,
      path: appendScopeToPath(
        `/pages/predictions/predictions?played_on=${encodeURIComponent(selectedDay.played_on || "")}`,
        scope
      )
    };
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
          notice: "",
          canGeneratePredictionCard: false
        }));
        return;
      }
      const paramsWithPaging = {
        ...scopeParams(selectedScope),
        played_on: options.playedOn || "",
        match_id: options.matchId || "",
        limit: PAGE_SIZE,
        offset: 0
      };
      const payload = await request("/api/predictions", paramsWithPaging, options);
      const predictions = (payload.predictions || []).map((item, index) => decoratePrediction(item, index));
      const pagination = payload.pagination || {};
      const canGeneratePredictionCard = predictions.length === 12
        && predictions.every((item) => item.markets.length === 6)
        && Boolean(payload.selected_day && payload.selected_day.played_on);
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
        loadingMore: false,
        loadMoreError: "",
        bandSummary: payload.band_summary || summarizeBands(predictions),
        notice: payload.notice || "",
        rosterSource: payload.roster_source || "none",
        modelMetadata: payload.model_metadata || {},
        scenario: payload.scenario || null,
        canGeneratePredictionCard
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
    if (!selectedScope || !this.data.predictionHasMore || this.data.loadingMore) {
      return;
    }
    this.setData({ loadingMore: true, loadMoreError: "" });
    request("/api/predictions", {
      ...scopeParams(selectedScope),
      played_on: selectedDay.played_on || "",
      limit: PAGE_SIZE,
      offset: this.data.predictionVisibleCount
    }).then((payload) => {
      const morePredictions = (payload.predictions || []).map((item, index) => (
        decoratePrediction(item, this.data.predictionVisibleCount + index)
      ));
      const predictions = this.data.predictions.concat(morePredictions);
      const pagination = payload.pagination || {};
      this.setData({
        predictions,
        predictionVisibleCount: predictions.length,
        predictionTotalCount: Number(pagination.total || this.data.predictionTotalCount || predictions.length),
        predictionHasMore: Boolean(pagination.has_more),
        loadingMore: false,
        loadMoreError: ""
      });
    }).catch((error) => {
      this.setData({ loadingMore: false, loadMoreError: error.message || "加载更多失败" });
    });
  },

  goCompetitions() {
    goCompetitions();
  },

  changeCompetition() {
    goCompetitions();
  },

  generatePredictionCard() {
    const scope = this.data.selectedScope;
    const selectedDay = this.data.selectedDay || {};
    if (!this.data.canGeneratePredictionCard || !scope || !selectedDay.played_on) {
      wx.showToast({ title: "当天预测名单尚未完整", icon: "none" });
      return;
    }
    wx.navigateTo({
      url: appendScopeToPath(
        `/pages/prediction-share-card/prediction-share-card?played_on=${encodeURIComponent(selectedDay.played_on)}`,
        scope
      )
    });
  }
});
