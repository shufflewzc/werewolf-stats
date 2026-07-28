const { request, assetUrl } = require("../../utils/api");
const { getCurrentPlayerForScope, getCurrentUser } = require("../../utils/auth");
const { getFollowedPlayers } = require("../../utils/follows");
const { take } = require("../../utils/format");
const {
  buildScopeFromCompetition,
  appendScopeToPath,
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

function sameScope(left, right) {
  if (!left || !right) {
    return false;
  }
  return ["competition", "season", "region", "series"]
    .every((key) => String(left[key] || "") === String(right[key] || ""));
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
      const progressStatus = row.progress_status || "";
      const fallbackBadges = [];
      if (row.regular_season_group) {
        fallbackBadges.push({
          text: row.regular_season_group,
          style: String(row.regular_season_group).indexOf("S") === 0 ? "gold" : "blue",
          kind: "group"
        });
      }
      if (progressStatus) {
        fallbackBadges.push({
          text: progressStatus,
          style: progressStatus === "直通"
            ? "orange"
            : (progressStatus === "晋级" ? "green" : (progressStatus === "淘汰" ? "red" : "gray")),
          kind: "progress"
        });
      }
      const badges = (Array.isArray(row.badges) ? row.badges : fallbackBadges)
        .map((badge) => ({
          ...badge,
          className: `is-${badge.style || "gray"}`
        }));
      return {
        key: `team:${row.team_id}`,
        type: "team",
        id: row.team_id,
        rank: row.rank,
        title: row.short_name || row.name,
        meta: `胜率 ${row.win_rate} · 出赛 ${row.matches_represented} 场`,
        value: row.points_total,
        valueLabel: "积分",
        regularSeasonGroup: row.regular_season_group || "",
        groupClass: String(row.regular_season_group || "").indexOf("S") === 0 ? "is-s" : "is-f",
        progressStatus,
        progressClass: progressStatus === "直通"
          ? "is-direct"
          : (progressStatus === "晋级" ? "is-promoted" : (progressStatus === "淘汰" ? "is-eliminated" : "")),
        badges
      };
    }
    if (key === "players") {
      return {
        key: `player:${row.player_id}`,
        type: "player",
        id: row.player_id,
        rank: row.rank,
        title: row.display_name,
        is_star_player: Boolean(row.is_star_player),
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
      is_star_player: Boolean(row.is_star_player),
      meta: `${row.team_name || "未绑定战队"} · 最近 ${row.latest_awarded_on || "待更新"}`,
      value: row.award_count,
      valueLabel: row.award_label || (key === "mvp" ? "MVP" : "SVP")
    };
  });
}

function selectedLeaderboardRows(key, stage, leaderboards, leaderboardsByStage, teamSectionsByStage, sectionKey) {
  const sections = (teamSectionsByStage && teamSectionsByStage[stage]) || [];
  if (key === "teams" && sections.length) {
    const section = sections.find((item) => item.key === sectionKey) || sections[0];
    return (section && section.rows) || [];
  }
  const boards = stage === "all"
    ? (leaderboards || {})
    : ((leaderboardsByStage || {})[stage] || {});
  return boards[key] || [];
}

async function hydrateFollowedPlayers(items, scope, options) {
  const follows = (items || []).slice(0, 5);
  const results = await Promise.all(follows.map(async (item) => {
    try {
      const payload = await request(`/api/players/${encodeURIComponent(item.player_id)}`, scopeParams(scope), options);
      const player = payload.player || {};
      const recent = (payload.recent_matches || [])[0] || {};
      return {
        ...item,
        display_name: player.name || player.display_name || item.display_name,
        team_name: player.team_name || item.team_name,
        is_star_player: Boolean(player.is_star_player),
        points_total: player.points_total || "--",
        rank: player.rank || "--",
        recent_label: recent.played_on ? `${recent.played_on} · ${recent.result_label || recent.result || "已出战"}` : "暂无比赛记录"
      };
    } catch (error) {
      return item;
    }
  }));
  return results;
}

Page({
  data: {
    loading: true,
    hasLoaded: false,
    refreshing: false,
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
    followedPlayers: [],
    searchKeyword: "",
    searchLoading: false,
    searchSearched: false,
    searchResults: [],
    leaderboardTabs: LEADERBOARD_TABS,
    teamSectionTabs: [],
    activeLeaderboard: "teams",
    leaderboardStages: [{ key: "all", label: "全部" }],
    activeLeaderboardStage: "all",
    activeTeamSection: "",
    leaderboards: {},
    leaderboardsByStage: {},
    teamLeaderboardSections: {},
    hasTeamSections: false,
    leaderboardRows: []
  },

  onShow() {
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData({ forceRefresh: true }).finally(() => wx.stopPullDownRefresh());
  },

  onShareAppMessage() {
    const scope = this.data.selectedScope;
    const latestDay = this.data.latestDay;
    return {
      title: latestDay
        ? `${scope && scope.competition ? scope.competition : "狼人杀赛事"} · ${latestDay.played_on} 比赛日`
        : `${scope && scope.competition ? scope.competition : "狼人杀赛事"} 数据中心`,
      path: appendScopeToPath("/pages/dashboard/dashboard", scope)
    };
  },

  async loadData(options = {}) {
    const requestId = (this._loadRequestId || 0) + 1;
    const hasLoaded = this.data.hasLoaded;
    this._loadRequestId = requestId;
    this.setData(hasLoaded
      ? { refreshing: true, error: "" }
      : { loading: true, refreshing: false, error: "" });
    try {
      const selectedScope = getSelectedScope();
      if (!selectedScope || !selectedScope.competition) {
        const competitions = await request("/api/competitions", {}, options);
        if (requestId !== this._loadRequestId) {
          return;
        }
        this.setData({
          loading: false,
          hasLoaded: true,
          refreshing: false,
          choosing: true,
          selectedScope: null,
          scopeLabel: "选择赛事",
          generatedAt: competitions.generated_at || "",
          hero: competitions.hero || {},
          metrics: take(competitions.metrics, 4),
          competitions: (competitions.cards || []).map(decorateCompetitionChoice),
          topTeams: [],
          topPlayers: [],
          matchDays: [],
          followedPlayers: [],
          leaderboards: {},
          leaderboardsByStage: {},
          teamLeaderboardSections: {},
          teamSectionTabs: [],
          activeTeamSection: "",
          hasTeamSections: false,
          leaderboardRows: []
        });
        return;
      }

      const payload = await request("/api/dashboard", scopeParams(selectedScope), options);
      if (requestId !== this._loadRequestId) {
        return;
      }
      const topPlayers = take(payload.top_players, 5).map((player) => ({
        ...player,
        photoUrl: assetUrl(player.photo)
      }));
      const leaderboards = payload.leaderboards || {};
      const leaderboardStages = payload.leaderboard_stages || [{ key: "all", label: "全部" }];
      const leaderboardsByStage = payload.leaderboards_by_stage || {};
      const regularSeasonTeamLeaderboards = payload.regular_season_team_leaderboards || {};
      const teamLeaderboardSections = {
        ...(payload.team_leaderboard_sections || {})
      };
      if (
        !Array.isArray(teamLeaderboardSections.regular_season)
        && Object.keys(regularSeasonTeamLeaderboards).length
      ) {
        teamLeaderboardSections.regular_season = Object.keys(regularSeasonTeamLeaderboards)
          .map((key) => ({
            key,
            label: `${key}组`,
            title: `${key}组常规赛榜`,
            rows: regularSeasonTeamLeaderboards[key] || []
          }));
      }
      const activeLeaderboard = this.data.activeLeaderboard || "teams";
      const currentStage = this.data.activeLeaderboardStage || "all";
      const activeLeaderboardStage = leaderboardStages.some((item) => item.key === currentStage)
        ? currentStage
        : "all";
      const activeStageSections = teamLeaderboardSections[activeLeaderboardStage] || [];
      const activeTeamSection = activeStageSections.some(
        (item) => item.key === this.data.activeTeamSection
      )
        ? this.data.activeTeamSection
        : ((activeStageSections[0] && activeStageSections[0].key) || "");
      const teamSectionTabs = activeStageSections.map((section) => ({
        key: section.key,
        label: section.label || section.key,
        title: section.title || `${section.label || section.key}榜`
      }));
      const hasTeamSections = Object.keys(teamLeaderboardSections).length > 0;
      const matchDays = take(payload.match_days, 4);
      const latestDay = matchDays[0] || null;
      const currentUser = getCurrentUser();
      const followedPlayerSeeds = getFollowedPlayers(selectedScope);
      const keepFollowedPlayers = sameScope(this.data.selectedScope, selectedScope);
      let myPlayer = null;
      let myEmptyText = "微信登录后，可以绑定选手并查看自己的赛事数据。";
      let myPrimaryActionText = "去登录";
      let myStatusLabel = "未登录";
      const boundPlayerIds = Array.isArray(currentUser && currentUser.bound_player_ids)
        ? currentUser.bound_player_ids
        : [];
      if (currentUser && boundPlayerIds.length) {
        try {
          const identity = await getCurrentPlayerForScope(selectedScope);
          if (requestId !== this._loadRequestId) {
            return;
          }
          if (identity.status === "matched" && identity.player) {
            const scopedPlayer = identity.player;
            myStatusLabel = "本赛季已绑定";
            myPrimaryActionText = "我的选手页";
            myPlayer = topPlayers.find((player) => player.player_id === scopedPlayer.player_id) || {
              ...scopedPlayer,
              team_name: scopedPlayer.team_name || "进入详情查看",
              points_total: "--",
              games_played: "--",
              photoUrl: assetUrl(scopedPlayer.photo)
            };
          } else if (identity.status === "conflict") {
            myStatusLabel = "绑定需要处理";
            myEmptyText = "同一赛季绑定了多个选手，请先到绑定管理中保留一个。";
            myPrimaryActionText = "管理绑定";
          } else {
            myStatusLabel = "本赛季未绑定";
            myEmptyText = "本赛季暂无已绑定选手，可以前往绑定对应的赛季档案。";
            myPrimaryActionText = "绑定选手";
          }
        } catch (error) {
          myStatusLabel = "身份加载失败";
          myEmptyText = error.message || "本赛季选手加载失败，请稍后重试。";
          myPrimaryActionText = "重试";
        }
      } else if (currentUser) {
        myStatusLabel = "未绑定选手";
        myEmptyText = "绑定选手后，这里会显示当前赛季的个人选手页。";
        myPrimaryActionText = "绑定选手";
      }
      this.setData({
        loading: false,
        hasLoaded: true,
        refreshing: false,
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
        leaderboardStages,
        activeLeaderboardStage,
        activeTeamSection,
        teamSectionTabs,
        leaderboardsByStage,
        teamLeaderboardSections,
        hasTeamSections,
        leaderboardRows: decorateLeaderboardRows(
          activeLeaderboard,
          selectedLeaderboardRows(
            activeLeaderboard,
            activeLeaderboardStage,
            leaderboards,
            leaderboardsByStage,
            teamLeaderboardSections,
            activeTeamSection
          )
        ),
        matchDays,
        latestDay,
        currentUser,
        myPlayer,
        myEmptyText,
        myPrimaryActionText,
        myStatusLabel,
        followedPlayers: keepFollowedPlayers ? this.data.followedPlayers : [],
        searchLoading: false
      });
      if (!followedPlayerSeeds.length) {
        if (this.data.followedPlayers.length) {
          this.setData({ followedPlayers: [] });
        }
        return;
      }
      hydrateFollowedPlayers(followedPlayerSeeds, selectedScope, options).then((followedPlayers) => {
        if (requestId !== this._loadRequestId || !sameScope(getSelectedScope(), selectedScope)) {
          return;
        }
        this.setData({ followedPlayers });
      });
    } catch (error) {
      if (requestId !== this._loadRequestId) {
        return;
      }
      if (hasLoaded) {
        this.setData({ refreshing: false });
        wx.showToast({ title: error.message || "刷新失败，请稍后重试", icon: "none" });
        return;
      }
      this.setData({
        loading: false,
        refreshing: false,
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
      if (keyword.length < 2) {
        this.setData({ searchLoading: false, searchResults: [] });
        return;
      }
      const payload = await request("/api/search", {
        ...scopeParams(selectedScope),
        q: keyword,
        limit: 100
      });
      this.setData({
        searchLoading: false,
        searchResults: (payload.results || []).map((item) => ({
          ...item,
          typeLabel: item.type_label,
          is_star_player: Boolean(item.is_star_player)
        }))
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
      return;
    }
    if (result.type === "team") {
      wx.navigateTo({ url: `/pages/team-detail/team-detail?team_id=${encodeURIComponent(result.id)}` });
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
    wx.navigateTo({
      url: `/pages/player-detail/player-detail?player_id=${encodeURIComponent(myPlayer.player_id)}&strict_player_id=1`
    });
  },

  openFollowedPlayer(event) {
    const playerId = event.currentTarget.dataset.playerId;
    if (!playerId) {
      return;
    }
    wx.navigateTo({ url: `/pages/player-detail/player-detail?player_id=${encodeURIComponent(playerId)}` });
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
    const stage = this.data.activeLeaderboardStage;
    this.setData({
      activeLeaderboard: key,
      leaderboardRows: decorateLeaderboardRows(
        key,
        selectedLeaderboardRows(
          key,
          stage,
          this.data.leaderboards,
          this.data.leaderboardsByStage,
          this.data.teamLeaderboardSections,
          this.data.activeTeamSection
        )
      )
    });
  },

  changeLeaderboardStage(event) {
    const stage = event.currentTarget.dataset.stage;
    const sections = this.data.teamLeaderboardSections[stage] || [];
    const activeSection = sections.some((item) => item.key === this.data.activeTeamSection)
      ? this.data.activeTeamSection
      : ((sections[0] && sections[0].key) || "");
    this.setData({
      activeLeaderboardStage: stage,
      activeTeamSection: activeSection,
      teamSectionTabs: sections.map((section) => ({
        key: section.key,
        label: section.label || section.key,
        title: section.title || `${section.label || section.key}榜`
      })),
      leaderboardRows: decorateLeaderboardRows(
        this.data.activeLeaderboard,
        selectedLeaderboardRows(
          this.data.activeLeaderboard,
          stage,
          this.data.leaderboards,
          this.data.leaderboardsByStage,
          this.data.teamLeaderboardSections,
          activeSection
        )
      )
    });
  },

  changeTeamSection(event) {
    const tier = String(event.currentTarget.dataset.tier || "");
    const sections = this.data.teamLeaderboardSections[this.data.activeLeaderboardStage] || [];
    if (!sections.some((item) => item.key === tier)) {
      return;
    }
    this.setData({
      activeTeamSection: tier,
      leaderboardRows: decorateLeaderboardRows(
        "teams",
        selectedLeaderboardRows(
          "teams",
          this.data.activeLeaderboardStage,
          this.data.leaderboards,
          this.data.leaderboardsByStage,
          this.data.teamLeaderboardSections,
          tier
        )
      )
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
