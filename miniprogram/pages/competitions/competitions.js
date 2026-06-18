const { request } = require("../../utils/api");
const { take } = require("../../utils/format");
const {
  buildScopeFromCompetition,
  getSelectedScope,
  setSelectedScope
} = require("../../utils/scope");

Page({
  data: {
    loading: true,
    error: "",
    selectedScope: null,
    view: "list",
    hero: {},
    metrics: [],
    cards: []
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
      const payload = await request("/api/competitions");
      const selectedScope = getSelectedScope();
      this.setData({
        loading: false,
        selectedScope,
        view: payload.view || "list",
        hero: payload.hero || {},
        metrics: take(payload.metrics, 4),
        cards: (payload.cards || []).map((card) => ({
          ...card,
          isSelected: Boolean(selectedScope && selectedScope.competition === card.competition_name),
          enterText: selectedScope && selectedScope.competition === card.competition_name ? "重新进入当前赛事" : "进入赛事"
        }))
      });
    } catch (error) {
      this.setData({
        loading: false,
        error: error.message || "赛事数据加载失败"
      });
    }
  },

  chooseCompetition(event) {
    const index = Number(event.currentTarget.dataset.index);
    const card = this.data.cards[index];
    setSelectedScope(buildScopeFromCompetition(card));
    wx.switchTab({ url: "/pages/dashboard/dashboard" });
  }
});
