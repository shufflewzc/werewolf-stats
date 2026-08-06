const { request } = require("../../utils/api");
const {
  buildScopeFromCompetition,
  getSelectedScope,
  setSelectedScope
} = require("../../utils/scope");

function decorateCompetitionCard(card, selectedScope) {
  const seasons = Array.isArray(card.seasons) ? card.seasons : [];
  const isSelectedCompetition = Boolean(selectedScope && selectedScope.competition === card.competition_name);
  const selectedSeasonIndex = isSelectedCompetition
    ? Math.max(0, seasons.indexOf(selectedScope.season))
    : 0;
  const selectedSeason = seasons[selectedSeasonIndex] || (isSelectedCompetition && selectedScope ? selectedScope.season : "") || "";
  const seasonStats = (card.season_stats && card.season_stats[selectedSeason]) || {};
  const isSelectedSeason = Boolean(isSelectedCompetition && selectedScope.season === selectedSeason);
  return {
    ...card,
    seasons,
    selectedSeason,
    selectedSeasonIndex,
    team_count: Number(seasonStats.team_count !== undefined ? seasonStats.team_count : card.team_count || 0),
    player_count: Number(seasonStats.player_count !== undefined ? seasonStats.player_count : card.player_count || 0),
    match_count: Number(seasonStats.match_count !== undefined ? seasonStats.match_count : card.match_count || 0),
    latest_played_on: seasonStats.latest_played_on || card.latest_played_on,
    hasMultipleSeasons: seasons.length > 1,
    isSelected: Boolean(isSelectedCompetition && isSelectedSeason),
    enterText: isSelectedCompetition && isSelectedSeason ? "重新进入当前赛季" : "进入该赛季"
  };
}

function fallbackCityGroups(cards) {
  const groupsByRegion = {};
  (cards || []).forEach((card) => {
    const regionName = String(card.region_name || "其他城市");
    if (!groupsByRegion[regionName]) {
      groupsByRegion[regionName] = {
        region_name: regionName,
        latest_played_on: card.latest_played_on || "待更新",
        cards: []
      };
    }
    groupsByRegion[regionName].cards.push(card);
  });
  return Object.keys(groupsByRegion).map((regionName) => ({
    ...groupsByRegion[regionName],
    competition_count: groupsByRegion[regionName].cards.length
  }));
}

function decorateCityGroups(rawGroups, cards, selectedScope, currentExpandedCity) {
  const sourceGroups = Array.isArray(rawGroups) && rawGroups.length
    ? rawGroups
    : fallbackCityGroups(cards);
  const cityGroups = sourceGroups
    .filter((group) => group && Array.isArray(group.cards) && group.cards.length)
    .map((group) => ({
      ...group,
      region_name: String(group.region_name || "其他城市"),
      competition_count: Number(group.competition_count || group.cards.length),
      latest_played_on: group.latest_played_on || "待更新",
      cards: group.cards.map((card) => decorateCompetitionCard(card, selectedScope)),
      expanded: false
    }));
  const availableCities = cityGroups.map((group) => group.region_name);
  const selectedCity = selectedScope && selectedScope.region;
  const expandedCity = availableCities.includes(currentExpandedCity)
    ? currentExpandedCity
    : (availableCities.includes(selectedCity) ? selectedCity : (availableCities[0] || ""));
  return {
    cityGroups: cityGroups.map((group) => ({
      ...group,
      expanded: group.region_name === expandedCity
    })),
    expandedCity,
    competitionCount: cityGroups.reduce((total, group) => total + group.cards.length, 0)
  };
}

Page({
  data: {
    loading: true,
    error: "",
    selectedScope: null,
    view: "list",
    hero: {},
    cityGroups: [],
    expandedCity: "",
    competitionCount: 0
  },

  onShow() {
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData({ forceRefresh: true }).finally(() => wx.stopPullDownRefresh());
  },

  async loadData(options = {}) {
    this.setData({ loading: true, error: "" });
    try {
      const payload = await request("/api/competitions", { grouped: "1" }, options);
      const selectedScope = getSelectedScope();
      const groupedData = decorateCityGroups(
        payload.city_groups,
        payload.cards,
        selectedScope,
        this.data.expandedCity
      );
      this.setData({
        loading: false,
        selectedScope,
        view: payload.view || "grouped",
        hero: {
          ...(payload.hero || {}),
          title: "赛事入口",
          copy: "按城市展开赛事，再选择要进入的赛季。"
        },
        ...groupedData
      });
    } catch (error) {
      this.setData({
        loading: false,
        error: error.message || "赛事数据加载失败"
      });
    }
  },

  toggleCity(event) {
    const cityIndex = Number(event.currentTarget.dataset.cityIndex);
    const city = this.data.cityGroups[cityIndex];
    if (!city) {
      return;
    }
    const shouldCollapse = city.region_name === this.data.expandedCity;
    this.setData({
      expandedCity: shouldCollapse ? "" : city.region_name,
      cityGroups: this.data.cityGroups.map((item, index) => ({
        ...item,
        expanded: !shouldCollapse && index === cityIndex
      }))
    });
  },

  chooseSeason(event) {
    const cityIndex = Number(event.currentTarget.dataset.cityIndex);
    const cardIndex = Number(event.currentTarget.dataset.cardIndex);
    const seasonIndex = Number(event.detail && event.detail.value);
    const city = this.data.cityGroups[cityIndex];
    const card = city && city.cards[cardIndex];
    if (!card) {
      return;
    }
    const selectedSeason = card.seasons[seasonIndex] || "";
    const seasonStats = (card.season_stats && card.season_stats[selectedSeason]) || {};
    const isSelectedSeason = Boolean(
      this.data.selectedScope
      && this.data.selectedScope.competition === card.competition_name
      && this.data.selectedScope.season === selectedSeason
    );
    this.setData({
      [`cityGroups[${cityIndex}].cards[${cardIndex}].selectedSeasonIndex`]: seasonIndex,
      [`cityGroups[${cityIndex}].cards[${cardIndex}].selectedSeason`]: selectedSeason,
      [`cityGroups[${cityIndex}].cards[${cardIndex}].team_count`]: Number(seasonStats.team_count !== undefined ? seasonStats.team_count : card.team_count || 0),
      [`cityGroups[${cityIndex}].cards[${cardIndex}].player_count`]: Number(seasonStats.player_count !== undefined ? seasonStats.player_count : card.player_count || 0),
      [`cityGroups[${cityIndex}].cards[${cardIndex}].match_count`]: Number(seasonStats.match_count !== undefined ? seasonStats.match_count : card.match_count || 0),
      [`cityGroups[${cityIndex}].cards[${cardIndex}].latest_played_on`]: seasonStats.latest_played_on || card.latest_played_on,
      [`cityGroups[${cityIndex}].cards[${cardIndex}].isSelected`]: isSelectedSeason,
      [`cityGroups[${cityIndex}].cards[${cardIndex}].enterText`]: isSelectedSeason ? "重新进入当前赛季" : "进入该赛季"
    });
  },

  chooseCompetition(event) {
    const cityIndex = Number(event.currentTarget.dataset.cityIndex);
    const cardIndex = Number(event.currentTarget.dataset.cardIndex);
    const city = this.data.cityGroups[cityIndex];
    const card = city && city.cards[cardIndex];
    if (!card) {
      return;
    }
    setSelectedScope(buildScopeFromCompetition(card, card.selectedSeason));
    wx.switchTab({ url: "/pages/dashboard/dashboard" });
  }
});
