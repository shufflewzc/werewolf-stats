const { request } = require("../../utils/api");
const { take } = require("../../utils/format");
const { getRequiredScope, goCompetitions, needsCompetitionState, scopeParams } = require("../../utils/scope");

function buildGuildOverview(payload) {
  const historySections = payload.history_sections || [];
  const teams = historySections.reduce((result, section) => result.concat(section.rows || []), []);
  const totalPoints = teams.reduce((sum, item) => sum + Number(item.points_total || 0), 0);
  const totalMatches = teams.reduce((sum, item) => sum + Number(item.matches || 0), 0);
  const topTeams = teams
    .slice()
    .sort((a, b) => Number(b.points_total || 0) - Number(a.points_total || 0))
    .slice(0, 3);
  return {
    cards: [
      { label: "历史战队", value: String(teams.length), copy: `${historySections.length} 个赛事` },
      { label: "累计积分", value: totalPoints.toFixed(1), copy: "历史赛季合计" },
      { label: "比赛覆盖", value: String(totalMatches), copy: "累计场次" }
    ],
    topTeams
  };
}

Page({
  data: {
    loading: true,
    error: "",
    guildId: "",
    selectedScope: null,
    needsCompetition: false,
    guild: {},
    metrics: [],
    overviewCards: [],
    topHistoryTeams: [],
    ongoingTeams: [],
    historySections: [],
    honors: []
  },

  onLoad(options) {
    this.setData({ guildId: decodeURIComponent(options.guild_id || "") });
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData().finally(() => wx.stopPullDownRefresh());
  },

  async loadData() {
    const guildId = this.data.guildId;
    if (!guildId) {
      this.setData({ loading: false, error: "缺少门派 ID" });
      return;
    }

    this.setData({ loading: true, error: "" });
    try {
      const selectedScope = getRequiredScope();
      if (!selectedScope) {
        this.setData(needsCompetitionState({
          guild: {},
          metrics: [],
          overviewCards: [],
          topHistoryTeams: [],
          ongoingTeams: [],
          historySections: [],
          honors: []
        }));
        return;
      }

      const payload = await request(`/api/guilds/${encodeURIComponent(guildId)}`, scopeParams(selectedScope));
      const guild = payload.guild || {};
      const overview = buildGuildOverview(payload);
      wx.setNavigationBarTitle({ title: guild.name || "门派详情" });
      this.setData({
        loading: false,
        selectedScope,
        needsCompetition: false,
        guild,
        metrics: take(payload.metrics, 4),
        overviewCards: overview.cards,
        topHistoryTeams: overview.topTeams,
        ongoingTeams: payload.ongoing_teams || [],
        historySections: payload.history_sections || [],
        honors: payload.honors || []
      });
    } catch (error) {
      this.setData({
        loading: false,
        error: error.message || "门派详情加载失败"
      });
    }
  },

  goCompetitions() {
    goCompetitions();
  },

  goGuilds() {
    wx.switchTab({ url: "/pages/guilds/guilds" });
  },

  changeCompetition() {
    goCompetitions();
  }
});
