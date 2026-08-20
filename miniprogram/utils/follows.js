const STORAGE_KEY = "werewolf:followedPlayers";
const MAX_FOLLOWS = 50;
const { request } = require("./api");
const { isCompleteScope } = require("./scope");

function readFollows() {
  const follows = wx.getStorageSync(STORAGE_KEY);
  return Array.isArray(follows) ? follows : [];
}

function sameScope(left, right) {
  return String(left || "") === String(right || "");
}

function isFollowed(playerId, scope) {
  return readFollows().some((item) => (
    item.player_id === playerId
    && sameScope(item.competition, scope && scope.competition)
    && sameScope(item.season, scope && scope.season)
  ));
}

function toggleFollow(player, scope) {
  const playerId = String((player && player.player_id) || "");
  if (!playerId || !isCompleteScope(scope)) {
    return false;
  }
  const follows = readFollows();
  const index = follows.findIndex((item) => (
    item.player_id === playerId
    && sameScope(item.competition, scope.competition)
    && sameScope(item.season, scope.season)
  ));
  if (index >= 0) {
    follows.splice(index, 1);
    wx.setStorageSync(STORAGE_KEY, follows);
    return false;
  }
  follows.unshift({
    player_id: playerId,
    display_name: player.display_name || player.name || playerId,
    team_name: player.team_name || "未绑定战队",
    is_star_player: Boolean(player.is_star_player),
    competition: scope.competition,
    season: scope.season || "",
    followed_at: Date.now()
  });
  wx.setStorageSync(STORAGE_KEY, follows.slice(0, MAX_FOLLOWS));
  return true;
}

function getFollowedPlayers(scope) {
  return readFollows()
    .filter((item) => (
      !scope || (
        sameScope(item.competition, scope.competition)
        && sameScope(item.season, scope.season)
      )
    ))
    .sort((left, right) => Number(right.followed_at || 0) - Number(left.followed_at || 0));
}

async function refreshFollowedPlayers(scope) {
  const follows = getFollowedPlayers(scope);
  const ids = follows.map((item) => item.player_id).filter(Boolean);
  if (!ids.length) {
    return follows;
  }
  try {
    const payload = await request("/api/miniprogram/player-labels", {
      player_ids: ids.join(",")
    }, { useCache: false });
    const labels = {};
    (payload.players || []).forEach((player) => {
      labels[player.player_id] = player;
    });
    const allFollows = readFollows().map((item) => labels[item.player_id]
      ? {
        ...item,
        display_name: labels[item.player_id].display_name || item.display_name,
        is_star_player: Boolean(labels[item.player_id].is_star_player)
      }
      : item);
    wx.setStorageSync(STORAGE_KEY, allFollows);
    return getFollowedPlayers(scope);
  } catch (error) {
    return follows;
  }
}

module.exports = {
  getFollowedPlayers,
  refreshFollowedPlayers,
  isFollowed,
  toggleFollow
};
