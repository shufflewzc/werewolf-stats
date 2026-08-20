const { request } = require("../../utils/api");
const { appendScopeToPath, applyScopeFromOptions, confirmScopeMismatch, getRequiredScope, goCompetitions, needsCompetitionState, sameScope, scopeActivationError, scopeParams } = require("../../utils/scope");

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
    canGeneratePredictionCard: false,
    switchingDay: false,
    switchingPlayedOn: "",
    switchDayError: ""
  },

  onLoad(options) {
    this.initialPlayedOn = options.played_on || "";
    this.initialMatchId = options.match_id || "";
    this._scopeReady = applyScopeFromOptions(options, { sourceLabel: "分享的预测页面" });
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
      this._scopeEntryBlocked = "";
    }
    const selectedPlayedOn = this.data.selectedDay && this.data.selectedDay.played_on;
    const loadPromise = this.loadData({
      playedOn: this.initialPlayedOn || selectedPlayedOn || "",
      matchId: this.initialMatchId,
      keepContent: Boolean(this.data.days.length)
    });
    this.initialPlayedOn = "";
    this.initialMatchId = "";
    return loadPromise;
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
    if (this._scopeEntryBlocked) {
      this.setData({ loading: false, error: this._scopeEntryBlocked });
      return false;
    }
    const requestId = Number(this.predictionRequestId || 0) + 1;
    const requestedPlayedOn = String(options.playedOn || "").trim();
    const keepContent = Boolean(options.keepContent && this.data.days.length);
    this.predictionRequestId = requestId;
    this.predictionLoadMoreRequestId = Number(this.predictionLoadMoreRequestId || 0) + 1;
    if (keepContent) {
      this.setData({
        switchingDay: true,
        switchingPlayedOn: requestedPlayedOn,
        switchDayError: "",
        error: "",
        loadingMore: false,
        loadMoreError: ""
      });
    } else {
      this.setData({
        loading: true,
        error: "",
        switchingDay: false,
        switchingPlayedOn: "",
        switchDayError: "",
        loadingMore: false,
        loadMoreError: ""
      });
    }
    const selectedScope = getRequiredScope();
    try {
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
          canGeneratePredictionCard: false,
          switchingDay: false,
          switchingPlayedOn: "",
          switchDayError: ""
        }));
        return false;
      }
      const paramsWithPaging = {
        ...scopeParams(selectedScope),
        played_on: requestedPlayedOn,
        match_id: options.matchId || "",
        limit: PAGE_SIZE,
        offset: 0
      };
      const payload = await request("/api/predictions", paramsWithPaging, options);
      if (requestId !== this.predictionRequestId || !sameScope(getRequiredScope(), selectedScope)) {
        return false;
      }
      const predictions = (payload.predictions || []).map((item, index) => decoratePrediction(item, index));
      const pagination = payload.pagination || {};
      const predictionIds = predictions.map((item) => String(item.player_id || "").trim());
      const requiredMarketKeys = ["lt_0", "lt_5", "lt_10", "gt_10", "gt_15", "gt_18"];
      const hasCompleteScoreProbabilities = predictions.every((item) => {
        const keys = new Set((item.markets || []).map((market) => String(market.key || "")));
        return requiredMarketKeys.every((key) => keys.has(key));
      });
      const canGeneratePredictionCard = predictions.length === 12
        && predictionIds.every(Boolean)
        && new Set(predictionIds).size === 12
        && Boolean(payload.selected_day && payload.selected_day.played_on)
        && hasCompleteScoreProbabilities;
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
        canGeneratePredictionCard,
        switchingDay: false,
        switchingPlayedOn: "",
        switchDayError: ""
      });
      return true;
    } catch (error) {
      if (requestId !== this.predictionRequestId || !sameScope(getRequiredScope(), selectedScope)) {
        return false;
      }
      const recovery = await confirmScopeMismatch(error, { sourceLabel: "该预测内容" });
      if (recovery) {
        if (recovery.accepted && !options.scopeMismatchRetried) {
          return this.loadData({ ...options, forceRefresh: true, scopeMismatchRetried: true });
        }
        if (!recovery.accepted) {
          this.setData({
            loading: false,
            switchingDay: false,
            switchingPlayedOn: "",
            error: scopeActivationError(recovery)
          });
          return false;
        }
      }
      const message = error.message || "胜率预测加载失败";
      if (keepContent) {
        this.setData({
          switchingDay: false,
          switchingPlayedOn: "",
          switchDayError: message
        });
      } else {
        this.setData({
          loading: false,
          error: message
        });
      }
      return false;
    }
  },

  chooseDay(event) {
    const currentDataset = (event.currentTarget && event.currentTarget.dataset) || {};
    const targetDataset = (event.target && event.target.dataset) || {};
    const playedOn = String(currentDataset.playedOn || targetDataset.playedOn || "").trim();
    const selectedPlayedOn = this.data.selectedDay && this.data.selectedDay.played_on;
    if (!playedOn || this.data.switchingPlayedOn === playedOn) {
      return Promise.resolve(false);
    }
    if (selectedPlayedOn === playedOn && !this.data.switchingDay) {
      return Promise.resolve(false);
    }
    return this.loadData({ playedOn, keepContent: true });
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
    const selectedDay = this.data.selectedDay || {};
    if (!selectedScope || !sameScope(selectedScope, this.data.selectedScope) || !this.data.predictionHasMore || this.data.loadingMore) {
      return false;
    }
    const requestId = Number(this.predictionLoadMoreRequestId || 0) + 1;
    const playedOn = selectedDay.played_on || "";
    const offset = this.data.predictionVisibleCount;
    this.predictionLoadMoreRequestId = requestId;
    this.setData({ loadingMore: true, loadMoreError: "" });
    try {
      const payload = await request("/api/predictions", {
        ...scopeParams(selectedScope),
        played_on: playedOn,
        limit: PAGE_SIZE,
        offset
      });
      if (
        requestId !== this.predictionLoadMoreRequestId
        || !sameScope(getRequiredScope(), selectedScope)
        || !sameScope(this.data.selectedScope, selectedScope)
        || (this.data.selectedDay && this.data.selectedDay.played_on) !== playedOn
        || this.data.predictionVisibleCount !== offset
      ) {
        if (requestId === this.predictionLoadMoreRequestId) {
          this.setData({ loadingMore: false });
        }
        return false;
      }
      const morePredictions = (payload.predictions || []).map((item, index) => (
        decoratePrediction(item, offset + index)
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
      return true;
    } catch (error) {
      if (requestId !== this.predictionLoadMoreRequestId) {
        return false;
      }
      if (!sameScope(getRequiredScope(), selectedScope)) {
        this.setData({ loadingMore: false });
        return false;
      }
      this.setData({ loadingMore: false, loadMoreError: error.message || "加载更多失败" });
      return false;
    }
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
