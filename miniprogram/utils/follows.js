const STORAGE_KEY = "werewolf:followedPlayers";
const MAX_FOLLOWS = 50;

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
  if (!playerId || !scope || !scope.competition) {
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

module.exports = {
  getFollowedPlayers,
  isFollowed,
  toggleFollow
};
