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

function decorateCompetitionChoice(card) {
  const seasons = Array.isArray(card.seasons) ? card.seasons : [];
  const selectedSeason = seasons[0] || "";
  const seasonStats = (card.season_stats && card.season_stats[selectedSeason]) || {};
  return {
    ...card,
    seasons,
    selectedSeason,
    selectedSeasonIndex: 0,
    team_count: Number(seasonStats.team_count !== undefined ? seasonStats.team_count : card.team_count || 0),
    player_count: Number(seasonStats.player_count !== undefined ? seasonStats.player_count : card.player_count || 0),
    match_count: Number(seasonStats.match_count !== undefined ? seasonStats.match_count : card.match_count || 0),
    latest_played_on: seasonStats.latest_played_on || card.latest_played_on,
    hasMultipleSeasons: seasons.length > 1
  };
}

function normalizeKeyword(value) {
  return String(value || "").trim().toLowerCase();
}

function matchText(item, keyword, fields) {
  const haystack = fields.map((field) => String(item[field] || "")).join(" ").toLowerCase();
  return haystack.indexOf(keyword) >= 0;
}

const LEADERBOARD_TABS = [
  { key: "teams", label: "战队积分" },
  { key: "players", label: "个人积分" },
  { key: "mvp", label: "个人MVP" },
  { key: "svp", label: "个人SVP" }
];

function decorateLeaderboardRows(key, rows) {
  return (rows || []).map((row) => {
    if (key === "teams") {
      return {
        key: `team:${row.team_id}`,
        type: "team",
        id: row.team_id,
        rank: row.rank,
        title: row.short_name || row.name,
        meta: `胜率 ${row.win_rate} · 出赛 ${row.matches_represented} 场`,
        value: row.points_total,
        valueLabel: "积分"
      };
    }
    if (key === "players") {
      return {
        key: `player:${row.player_id}`,
        type: "player",
        id: row.player_id,
        rank: row.rank,
        title: row.display_name,
        meta: `${row.team_name || "未绑定战队"} · 出场 ${row.games_played} 局`,
        value: row.points_total,
        valueLabel: "积分"
      };
    }
    return {
      key: `${key}:${row.player_id}`,
      type: "player",
      id: row.player_id,
      rank: row.rank,
      title: row.display_name,
      meta: `${row.team_name || "未绑定战队"} · 最近 ${row.latest_awarded_on || "待更新"}`,
      value: row.award_count,
      valueLabel: row.award_label || (key === "mvp" ? "MVP" : "SVP")
    };
  });
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
    myEmptyText: "微信登录后，可以绑定选手并查看自己的赛事数据。",
    myPrimaryActionText: "去登录",
    myStatusLabel: "未登录",
    searchKeyword: "",
    searchLoading: false,
    searchSearched: false,
    searchResults: [],
    leaderboardTabs: LEADERBOARD_TABS,
    activeLeaderboard: "teams",
    leaderboards: {},
    leaderboardRows: []
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
          competitions: (competitions.cards || []).map(decorateCompetitionChoice),
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
      const leaderboards = payload.leaderboards || {};
      const activeLeaderboard = this.data.activeLeaderboard || "teams";
      const matchDays = take(payload.match_days, 4);
      const latestDay = matchDays[0] || null;
      const currentUser = getCurrentUser();
      let myPlayer = null;
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
      } else if (currentUser) {
        myStatusLabel = "未绑定选手";
        myEmptyText = "绑定选手后，这里会显示你的赛事入口和个人选手页。";
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
        leaderboards,
        leaderboardRows: decorateLeaderboardRows(activeLeaderboard, leaderboards[activeLeaderboard]),
        matchDays,
        latestDay,
        currentUser,
        myPlayer,
        myEmptyText,
        myPrimaryActionText,
        myStatusLabel,
        searchLoading: false
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

  updateSearchKeyword(event) {
    this.setData({
      searchKeyword: event.detail.value || "",
      searchSearched: false,
      searchResults: []
    });
  },

  clearSearch() {
    this.setData({
      searchKeyword: "",
      searchLoading: false,
      searchSearched: false,
      searchResults: []
    });
  },

  async searchSeason() {
    const keyword = normalizeKeyword(this.data.searchKeyword);
    const selectedScope = this.data.selectedScope;
    if (!keyword || !selectedScope) {
      this.setData({ searchSearched: true, searchResults: [] });
      return;
    }
    this.setData({ searchLoading: true, searchSearched: true, searchResults: [] });
    try {
      const params = scopeParams(selectedScope);
      const [playersPayload, guildsPayload] = await Promise.all([
        request("/api/players", { ...params, limit: 100, offset: 0 }),
        request("/api/guilds", params)
      ]);
      const playerResults = (playersPayload.players || [])
        .filter((player) => matchText(player, keyword, ["display_name", "player_id", "team_name"]))
        .slice(0, 8)
        .map((player) => ({
          key: `player:${player.player_id}`,
          type: "player",
          typeLabel: "选手",
          id: player.player_id,
          title: player.display_name || player.player_id,
          subtitle: `${player.team_name || "未绑定门派"} · 积分 ${player.points_total || "--"} · 胜率 ${player.win_rate || "--"}`
        }));
      const guildResults = (guildsPayload.cards || [])
        .filter((guild) => matchText(guild, keyword, ["name", "short_name", "notes"]))
        .slice(0, 6)
        .map((guild) => ({
          key: `guild:${guild.guild_id}`,
          type: "guild",
          typeLabel: "门派",
          id: guild.guild_id,
          title: guild.name || guild.short_name || guild.guild_id,
          subtitle: `${guild.short_name || "门派"} · 覆盖 ${guild.match_count || 0} 场 · 荣誉 ${guild.honor_count || 0}`
        }));
      this.setData({
        searchLoading: false,
        searchResults: playerResults.concat(guildResults).slice(0, 12)
      });
    } catch (error) {
      this.setData({
        searchLoading: false,
        searchResults: [{
          key: "error",
          type: "error",
          typeLabel: "错误",
          id: "",
          title: error.message || "搜索失败",
          subtitle: "请稍后重试"
        }]
      });
    }
  },

  openSearchResult(event) {
    const index = Number(event.currentTarget.dataset.index);
    const result = this.data.searchResults[index];
    if (!result || !result.id || result.type === "error") {
      return;
    }
    if (result.type === "player") {
      wx.navigateTo({ url: `/pages/player-detail/player-detail?player_id=${encodeURIComponent(result.id)}` });
      return;
    }
    if (result.type === "guild") {
      wx.navigateTo({ url: `/pages/guild-detail/guild-detail?guild_id=${encodeURIComponent(result.id)}` });
    }
  },

  onTeamImageError(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (!Number.isFinite(index)) {
      return;
    }
    this.setData({ [`topTeams[${index}].logoUrl`]: "" });
  },

  onPlayerImageError(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (!Number.isFinite(index)) {
      return;
    }
    this.setData({ [`topPlayers[${index}].photoUrl`]: "" });
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

  changeLeaderboard(event) {
    const key = event.currentTarget.dataset.key;
    const leaderboards = this.data.leaderboards || {};
    this.setData({
      activeLeaderboard: key,
      leaderboardRows: decorateLeaderboardRows(key, leaderboards[key])
    });
  },

  openLeaderboardRow(event) {
    const row = this.data.leaderboardRows[Number(event.currentTarget.dataset.index)];
    if (!row || !row.id) {
      return;
    }
    if (row.type === "player") {
      wx.navigateTo({ url: `/pages/player-detail/player-detail?player_id=${encodeURIComponent(row.id)}` });
      return;
    }
    if (row.type === "team") {
      wx.navigateTo({ url: `/pages/team-detail/team-detail?team_id=${encodeURIComponent(row.id)}` });
    }
  },

  chooseCompetition(event) {
    const index = Number(event.currentTarget.dataset.index);
    const card = this.data.competitions[index];
    if (!card) {
      return;
    }
    const scope = buildScopeFromCompetition(card, card.selectedSeason);
    setSelectedScope(scope);
    this.loadData();
  },

  chooseSeason(event) {
    const index = Number(event.currentTarget.dataset.index);
    const seasonIndex = Number(event.detail && event.detail.value);
    const card = this.data.competitions[index];
    if (!card) {
      return;
    }
    const selectedSeason = card.seasons[seasonIndex] || "";
    const seasonStats = (card.season_stats && card.season_stats[selectedSeason]) || {};
    this.setData({
      [`competitions[${index}].selectedSeasonIndex`]: seasonIndex,
      [`competitions[${index}].selectedSeason`]: selectedSeason,
      [`competitions[${index}].team_count`]: Number(seasonStats.team_count !== undefined ? seasonStats.team_count : card.team_count || 0),
      [`competitions[${index}].player_count`]: Number(seasonStats.player_count !== undefined ? seasonStats.player_count : card.player_count || 0),
      [`competitions[${index}].match_count`]: Number(seasonStats.match_count !== undefined ? seasonStats.match_count : card.match_count || 0),
      [`competitions[${index}].latest_played_on`]: seasonStats.latest_played_on || card.latest_played_on
    });
  },

  changeCompetition() {
    clearSelectedScope();
    this.loadData();
  }
});
