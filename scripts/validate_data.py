#!/usr/bin/env python3

from __future__ import annotations

import re
import sys
from datetime import date
from typing import Any

from sqlite_store import load_repository_data, load_users

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
MATCH_ID_PATTERN = re.compile(r"^[a-z0-9]{1,6}-[a-z0-9]{1,8}-\d{6}-\d{2}$")
VALID_STAGES = {"placement", "regular_season", "playoffs", "finals", "showmatch"}
VALID_CAMPS = {"villagers", "werewolves", "third_party"}
VALID_WINNING_CAMPS = {"villagers", "werewolves", "third_party"}
VALID_RESULTS = {"win", "loss"}
VALID_STANCE_RESULTS = {"correct", "incorrect", "none"}
VALID_SCORE_MODELS = {"standard", "jingcheng_daily"}
MATCH_SCORE_COMPONENT_FIELDS = {
    "result_points",
    "vote_points",
    "behavior_points",
    "special_points",
    "adjustment_points",
}


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def expect_keys(obj: dict[str, Any], required: set[str], label: str) -> list[str]:
    errors: list[str] = []
    missing = required - obj.keys()
    extra = obj.keys() - required

    if missing:
        errors.append(f"{label}: missing keys {sorted(missing)}")
    if extra:
        errors.append(f"{label}: unexpected keys {sorted(extra)}")
    return errors


def validate_iso_date(value: Any, label: str) -> list[str]:
    if not isinstance(value, str):
        return [f"{label}: expected ISO date string"]

    try:
        date.fromisoformat(value)
    except ValueError:
        return [f"{label}: invalid date {value!r}"]
    return []


def validate_slug(value: Any, label: str) -> list[str]:
    if not isinstance(value, str) or not SLUG_PATTERN.match(value):
        return [f"{label}: expected lowercase slug-like string"]
    return []


def validate_non_empty_string(value: Any, label: str) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return [f"{label}: expected non-empty string"]
    return []


def validate_string(value: Any, label: str) -> list[str]:
    if not isinstance(value, str):
        return [f"{label}: expected string"]
    return []


def validate_teams(teams: Any) -> tuple[list[str], set[str], dict[str, set[str]]]:
    errors: list[str] = []
    team_ids: set[str] = set()
    team_members: dict[str, set[str]] = {}

    if not isinstance(teams, list):
        return ["teams: top-level value must be an array"], team_ids, team_members

    required_keys = {
        "team_id",
        "name",
        "short_name",
        "logo",
        "active",
        "founded_on",
        "competition_name",
        "season_name",
        "guild_id",
        "captain_player_id",
        "stage_groups",
        "members",
        "notes",
    }
    seen_member_ids: set[str] = set()

    for index, team in enumerate(teams):
        label = f"teams[{index}]"
        if not isinstance(team, dict):
            errors.append(f"{label}: expected object")
            continue

        errors.extend(expect_keys(team, required_keys, label))

        team_id = team.get("team_id")
        errors.extend(validate_slug(team_id, f"{label}.team_id"))
        if isinstance(team_id, str) and SLUG_PATTERN.match(team_id):
            if team_id in team_ids:
                errors.append(f"{label}.team_id: duplicate team_id {team_id!r}")
            else:
                team_ids.add(team_id)

        errors.extend(validate_non_empty_string(team.get("name"), f"{label}.name"))
        errors.extend(
            validate_non_empty_string(team.get("short_name"), f"{label}.short_name")
        )
        errors.extend(validate_non_empty_string(team.get("logo"), f"{label}.logo"))

        if not isinstance(team.get("active"), bool):
            errors.append(f"{label}.active: expected boolean")

        errors.extend(validate_iso_date(team.get("founded_on"), f"{label}.founded_on"))
        errors.extend(
            validate_non_empty_string(
                team.get("competition_name"), f"{label}.competition_name"
            )
        )
        errors.extend(
            validate_non_empty_string(team.get("season_name"), f"{label}.season_name")
        )
        guild_id = team.get("guild_id")
        if not isinstance(guild_id, str):
            errors.append(f"{label}.guild_id: expected string")
        elif guild_id.strip():
            errors.extend(validate_slug(guild_id, f"{label}.guild_id"))

        members = team.get("members")
        member_set: set[str] = set()
        if not isinstance(members, list):
            errors.append(f"{label}.members: expected array of player IDs")
        else:
            for member_index, member in enumerate(members):
                member_label = f"{label}.members[{member_index}]"
                errors.extend(validate_slug(member, member_label))
                if isinstance(member, str):
                    if member in member_set:
                        errors.append(f"{member_label}: duplicate member {member!r} in team")
                    else:
                        member_set.add(member)

                    if member in seen_member_ids:
                        errors.append(f"{member_label}: player {member!r} appears in multiple teams")
                    else:
                        seen_member_ids.add(member)

        if isinstance(team_id, str) and SLUG_PATTERN.match(team_id):
            team_members[team_id] = member_set

        captain_player_id = team.get("captain_player_id")
        if captain_player_id is not None:
            errors.extend(validate_slug(captain_player_id, f"{label}.captain_player_id"))
            if isinstance(captain_player_id, str) and captain_player_id not in member_set:
                errors.append(
                    f"{label}.captain_player_id: captain must also appear in team members"
                )
        stage_groups = team.get("stage_groups")
        if not isinstance(stage_groups, list):
            errors.append(f"{label}.stage_groups: expected array")
        else:
            seen_stages: set[str] = set()
            for group_index, group in enumerate(stage_groups):
                group_label = f"{label}.stage_groups[{group_index}]"
                if not isinstance(group, dict):
                    errors.append(f"{group_label}: expected object")
                    continue
                errors.extend(expect_keys(group, {"stage", "group_label"}, group_label))
                stage = group.get("stage")
                if stage not in VALID_STAGES:
                    errors.append(f"{group_label}.stage: expected one of {sorted(VALID_STAGES)}")
                elif stage in seen_stages:
                    errors.append(f"{group_label}.stage: duplicate stage {stage!r}")
                else:
                    seen_stages.add(stage)
                errors.extend(validate_non_empty_string(group.get("group_label"), f"{group_label}.group_label"))

        if not isinstance(team.get("notes"), str):
            errors.append(f"{label}.notes: expected string")

    return errors, team_ids, team_members


def validate_guilds(
    guilds: Any,
    usernames: set[str],
) -> tuple[list[str], set[str]]:
    errors: list[str] = []
    guild_ids: set[str] = set()
    if not isinstance(guilds, list):
        return ["guilds: top-level value must be an array"], guild_ids

    required_keys = {
        "guild_id",
        "name",
        "short_name",
        "logo",
        "active",
        "founded_on",
        "leader_username",
        "manager_usernames",
        "honors",
        "notes",
    }

    for index, guild in enumerate(guilds):
        label = f"guilds[{index}]"
        if not isinstance(guild, dict):
            errors.append(f"{label}: expected object")
            continue

        errors.extend(expect_keys(guild, required_keys, label))
        guild_id = guild.get("guild_id")
        errors.extend(validate_slug(guild_id, f"{label}.guild_id"))
        if isinstance(guild_id, str) and SLUG_PATTERN.match(guild_id):
            if guild_id in guild_ids:
                errors.append(f"{label}.guild_id: duplicate guild_id {guild_id!r}")
            else:
                guild_ids.add(guild_id)
        errors.extend(validate_non_empty_string(guild.get("name"), f"{label}.name"))
        errors.extend(
            validate_non_empty_string(guild.get("short_name"), f"{label}.short_name")
        )
        errors.extend(validate_non_empty_string(guild.get("logo"), f"{label}.logo"))
        if not isinstance(guild.get("active"), bool):
            errors.append(f"{label}.active: expected boolean")
        errors.extend(validate_iso_date(guild.get("founded_on"), f"{label}.founded_on"))
        leader_username = guild.get("leader_username")
        if not isinstance(leader_username, str) or not leader_username.strip():
            errors.append(f"{label}.leader_username: expected non-empty string")
        elif leader_username not in usernames:
            errors.append(f"{label}.leader_username: unknown username {leader_username!r}")
        manager_usernames = guild.get("manager_usernames")
        if not isinstance(manager_usernames, list):
            errors.append(f"{label}.manager_usernames: expected array")
        else:
            seen_usernames: set[str] = set()
            for manager_index, username in enumerate(manager_usernames):
                manager_label = f"{label}.manager_usernames[{manager_index}]"
                if not isinstance(username, str) or not username.strip():
                    errors.append(f"{manager_label}: expected non-empty string")
                    continue
                if username not in usernames:
                    errors.append(f"{manager_label}: unknown username {username!r}")
                elif username in seen_usernames:
                    errors.append(f"{manager_label}: duplicate username {username!r}")
                else:
                    seen_usernames.add(username)
        honors = guild.get("honors")
        if not isinstance(honors, list):
            errors.append(f"{label}.honors: expected array")
        else:
            for honor_index, honor in enumerate(honors):
                honor_label = f"{label}.honors[{honor_index}]"
                if not isinstance(honor, dict):
                    errors.append(f"{honor_label}: expected object")
                    continue
                errors.extend(expect_keys(honor, {"title", "team_name", "scope"}, honor_label))
                errors.extend(validate_non_empty_string(honor.get("title"), f"{honor_label}.title"))
                errors.extend(validate_non_empty_string(honor.get("team_name"), f"{honor_label}.team_name"))
                errors.extend(validate_non_empty_string(honor.get("scope"), f"{honor_label}.scope"))
        if not isinstance(guild.get("notes"), str):
            errors.append(f"{label}.notes: expected string")

    return errors, guild_ids


def validate_players(
    players: Any, team_ids: set[str]
) -> tuple[list[str], set[str], dict[str, str]]:
    errors: list[str] = []
    player_ids: set[str] = set()
    player_teams: dict[str, str] = {}

    if not isinstance(players, list):
        return ["players: top-level value must be an array"], player_ids, player_teams

    required_keys = {
        "player_id",
        "display_name",
        "team_id",
        "photo",
        "aliases",
        "active",
        "joined_on",
        "notes",
    }

    for index, player in enumerate(players):
        label = f"players[{index}]"
        if not isinstance(player, dict):
            errors.append(f"{label}: expected object")
            continue

        errors.extend(expect_keys(player, required_keys, label))

        player_id = player.get("player_id")
        errors.extend(validate_slug(player_id, f"{label}.player_id"))
        if isinstance(player_id, str) and SLUG_PATTERN.match(player_id):
            if player_id in player_ids:
                errors.append(f"{label}.player_id: duplicate player_id {player_id!r}")
            else:
                player_ids.add(player_id)

        errors.extend(
            validate_non_empty_string(player.get("display_name"), f"{label}.display_name")
        )

        team_id = player.get("team_id")
        errors.extend(validate_slug(team_id, f"{label}.team_id"))
        if isinstance(team_id, str) and team_id not in team_ids:
            errors.append(f"{label}.team_id: unknown team_id {team_id!r}")

        if isinstance(player_id, str) and isinstance(team_id, str):
            player_teams[player_id] = team_id

        errors.extend(validate_non_empty_string(player.get("photo"), f"{label}.photo"))

        aliases = player.get("aliases")
        if not isinstance(aliases, list) or not all(
            isinstance(alias, str) for alias in aliases
        ):
            errors.append(f"{label}.aliases: expected array of strings")

        if not isinstance(player.get("active"), bool):
            errors.append(f"{label}.active: expected boolean")

        errors.extend(validate_iso_date(player.get("joined_on"), f"{label}.joined_on"))

        if not isinstance(player.get("notes"), str):
            errors.append(f"{label}.notes: expected string")

    return errors, player_ids, player_teams


def validate_rosters(
    team_members: dict[str, set[str]], player_ids: set[str], player_teams: dict[str, str]
) -> list[str]:
    errors: list[str] = []

    for team_id, members in team_members.items():
        for player_id in members:
            if player_id not in player_ids:
                errors.append(
                    f"teams[{team_id}].members: unknown player_id {player_id!r}"
                )
                continue

            if player_teams.get(player_id) != team_id:
                errors.append(
                    f"teams[{team_id}].members: player {player_id!r} does not point back "
                    f"to team {team_id!r}"
                )

    for player_id, team_id in player_teams.items():
        if player_id not in team_members.get(team_id, set()):
            errors.append(
                f"players[{player_id}].team_id: player is missing from team {team_id!r} roster"
            )

    return errors


def expected_result(winning_camp: str, participant_camp: str) -> str:
    if participant_camp == winning_camp:
        return "win"
    return "loss"


def validate_matches(matches: Any, team_ids: set[str], player_ids: set[str]) -> list[str]:
    errors: list[str] = []
    match_ids: set[str] = set()

    if not isinstance(matches, list):
        return ["matches: top-level value must be an array"]

    required_keys = {
        "match_id",
        "competition_name",
        "season",
        "stage",
        "round",
        "game_no",
        "score_model",
        "played_on",
        "group_label",
        "table_label",
        "format",
        "duration_minutes",
        "winning_camp",
        "mvp_player_id",
        "svp_player_id",
        "scapegoat_player_id",
        "players",
        "notes",
    }
    required_player_keys = {
        "player_id",
        "team_id",
        "seat",
        "role",
        "camp",
        "result",
        "points_earned",
        "result_points",
        "vote_points",
        "behavior_points",
        "special_points",
        "adjustment_points",
        "stance_result",
        "notes",
    }

    for index, match in enumerate(matches):
        label = f"matches[{index}]"
        if not isinstance(match, dict):
            errors.append(f"{label}: expected object")
            continue

        errors.extend(expect_keys(match, required_keys, label))

        match_id = match.get("match_id")
        errors.extend(validate_slug(match_id, f"{label}.match_id"))
        if isinstance(match_id, str) and SLUG_PATTERN.match(match_id):
            if not MATCH_ID_PATTERN.match(match_id):
                errors.append(
                    f"{label}.match_id: expected format citycode-seasoncode-yymmdd-xx"
                )
            if match_id in match_ids:
                errors.append(f"{label}.match_id: duplicate match_id {match_id!r}")
            else:
                match_ids.add(match_id)

        errors.extend(
            validate_non_empty_string(
                match.get("competition_name"), f"{label}.competition_name"
            )
        )
        errors.extend(validate_non_empty_string(match.get("season"), f"{label}.season"))

        stage = match.get("stage")
        if stage not in VALID_STAGES:
            errors.append(f"{label}.stage: expected one of {sorted(VALID_STAGES)}")

        round_value = match.get("round")
        if not isinstance(round_value, int) or isinstance(round_value, bool) or round_value < 1:
            errors.append(f"{label}.round: expected integer >= 1")

        game_no = match.get("game_no")
        if not isinstance(game_no, int) or isinstance(game_no, bool) or game_no < 1:
            errors.append(f"{label}.game_no: expected integer >= 1")

        score_model = match.get("score_model")
        if score_model not in VALID_SCORE_MODELS:
            errors.append(
                f"{label}.score_model: expected one of {sorted(VALID_SCORE_MODELS)}"
            )

        errors.extend(validate_iso_date(match.get("played_on"), f"{label}.played_on"))
        errors.extend(validate_string(match.get("group_label"), f"{label}.group_label"))
        errors.extend(
            validate_non_empty_string(match.get("table_label"), f"{label}.table_label")
        )
        errors.extend(validate_non_empty_string(match.get("format"), f"{label}.format"))

        is_placeholder_match = str(match.get("format") or "").strip() == "待补录"
        winning_camp = match.get("winning_camp")
        valid_winning_camps = (
            VALID_WINNING_CAMPS | {"draw"} if is_placeholder_match else VALID_WINNING_CAMPS
        )
        if winning_camp not in valid_winning_camps:
            errors.append(
                f"{label}.winning_camp: expected one of {sorted(valid_winning_camps)}"
            )

        duration_minutes = match.get("duration_minutes")
        if not isinstance(duration_minutes, int) or isinstance(duration_minutes, bool):
            errors.append(f"{label}.duration_minutes: expected integer")
        elif is_placeholder_match:
            if duration_minutes < 0:
                errors.append(f"{label}.duration_minutes: must be >= 0")
        elif duration_minutes < 1:
            errors.append(f"{label}.duration_minutes: must be >= 1")

        participants = match.get("players")
        participant_ids_in_match: set[str] = set()
        participant_camps_by_id: dict[str, str] = {}
        if not isinstance(participants, list):
            errors.append(f"{label}.players: expected array")
        elif not participants and not is_placeholder_match:
            errors.append(f"{label}.players: expected at least one participant")
        else:
            seen_seats: set[int] = set()
            seen_players: set[str] = set()

            for player_index, participant in enumerate(participants):
                participant_label = f"{label}.players[{player_index}]"
                if not isinstance(participant, dict):
                    errors.append(f"{participant_label}: expected object")
                    continue

                errors.extend(
                    expect_keys(participant, required_player_keys, participant_label)
                )

                participant_id = participant.get("player_id")
                errors.extend(validate_slug(participant_id, f"{participant_label}.player_id"))
                if isinstance(participant_id, str):
                    if participant_id not in player_ids:
                        errors.append(
                            f"{participant_label}.player_id: unknown player_id {participant_id!r}"
                        )
                    elif participant_id in seen_players:
                        errors.append(
                            f"{participant_label}.player_id: duplicate player in match {participant_id!r}"
                        )
                    else:
                        seen_players.add(participant_id)
                        participant_ids_in_match.add(participant_id)

                participant_team_id = participant.get("team_id")
                errors.extend(validate_slug(participant_team_id, f"{participant_label}.team_id"))
                if isinstance(participant_team_id, str) and participant_team_id not in team_ids:
                    errors.append(
                        f"{participant_label}.team_id: unknown team_id {participant_team_id!r}"
                    )

                seat = participant.get("seat")
                if not isinstance(seat, int) or isinstance(seat, bool):
                    errors.append(f"{participant_label}.seat: expected integer")
                elif seat < 1:
                    errors.append(f"{participant_label}.seat: must be >= 1")
                elif seat in seen_seats:
                    errors.append(f"{participant_label}.seat: duplicate seat {seat}")
                else:
                    seen_seats.add(seat)

                role = participant.get("role")
                if not isinstance(role, str):
                    errors.append(f"{participant_label}.role: expected string")

                camp = participant.get("camp")
                if camp not in VALID_CAMPS:
                    errors.append(
                        f"{participant_label}.camp: expected one of {sorted(VALID_CAMPS)}"
                    )
                elif isinstance(participant_id, str) and participant_id in participant_ids_in_match:
                    participant_camps_by_id[participant_id] = camp

                result = participant.get("result")
                if result not in VALID_RESULTS:
                    errors.append(
                        f"{participant_label}.result: expected one of {sorted(VALID_RESULTS)}"
                    )
                elif (
                    isinstance(winning_camp, str)
                    and winning_camp in VALID_WINNING_CAMPS
                    and isinstance(camp, str)
                    and camp in VALID_CAMPS
                    and result != expected_result(winning_camp, camp)
                ):
                    errors.append(
                        f"{participant_label}.result: expected {expected_result(winning_camp, camp)!r} "
                        f"for camp {camp!r} when winning_camp is {winning_camp!r}"
                    )

                points_earned = participant.get("points_earned")
                if not is_number(points_earned):
                    errors.append(f"{participant_label}.points_earned: expected number")

                for component_name in sorted(MATCH_SCORE_COMPONENT_FIELDS):
                    component_value = participant.get(component_name)
                    if not is_number(component_value):
                        errors.append(
                            f"{participant_label}.{component_name}: expected number"
                        )

                if (
                    score_model == "jingcheng_daily"
                    and is_number(points_earned)
                    and all(
                        is_number(participant.get(component_name))
                        for component_name in MATCH_SCORE_COMPONENT_FIELDS
                    )
                ):
                    breakdown_total = round(
                        sum(
                            float(participant.get(component_name) or 0.0)
                            for component_name in MATCH_SCORE_COMPONENT_FIELDS
                        ),
                        2,
                    )
                    if round(float(points_earned), 2) != breakdown_total:
                        errors.append(
                            f"{participant_label}.points_earned: expected {breakdown_total:.2f} "
                            "from breakdown when score_model is 'jingcheng_daily'"
                        )

                stance_result = participant.get("stance_result")
                if stance_result not in VALID_STANCE_RESULTS:
                    errors.append(
                        f"{participant_label}.stance_result: expected one of {sorted(VALID_STANCE_RESULTS)}"
                    )

                if not isinstance(participant.get("notes"), str):
                    errors.append(f"{participant_label}.notes: expected string")

        mvp_player_id = match.get("mvp_player_id")
        if isinstance(mvp_player_id, str) and not mvp_player_id.strip() and is_placeholder_match:
            pass
        else:
            errors.extend(validate_slug(mvp_player_id, f"{label}.mvp_player_id"))
        if (
            isinstance(mvp_player_id, str)
            and mvp_player_id.strip()
            and mvp_player_id not in participant_ids_in_match
        ):
            errors.append(
                f"{label}.mvp_player_id: expected one of this match's participant IDs"
            )

        svp_player_id = match.get("svp_player_id")
        if isinstance(svp_player_id, str) and not svp_player_id.strip() and is_placeholder_match:
            pass
        else:
            errors.extend(validate_slug(svp_player_id, f"{label}.svp_player_id"))
        if (
            isinstance(svp_player_id, str)
            and svp_player_id.strip()
            and svp_player_id not in participant_ids_in_match
        ):
            errors.append(
                f"{label}.svp_player_id: expected one of this match's participant IDs"
            )
        if (
            isinstance(mvp_player_id, str)
            and isinstance(svp_player_id, str)
            and mvp_player_id
            and svp_player_id
            and mvp_player_id == svp_player_id
        ):
            errors.append(f"{label}: mvp_player_id and svp_player_id must be different")

        scapegoat_player_id = match.get("scapegoat_player_id")
        if is_placeholder_match and isinstance(scapegoat_player_id, str) and not scapegoat_player_id.strip():
            pass
        elif winning_camp in {"villagers", "third_party"}:
            if not isinstance(scapegoat_player_id, str):
                errors.append(f"{label}.scapegoat_player_id: expected string")
            elif scapegoat_player_id.strip():
                errors.append(f"{label}.scapegoat_player_id: must be empty when non-werewolves win")
        else:
            errors.extend(
                validate_slug(scapegoat_player_id, f"{label}.scapegoat_player_id")
            )
            if (
                isinstance(scapegoat_player_id, str)
                and scapegoat_player_id not in participant_ids_in_match
            ):
                errors.append(
                    f"{label}.scapegoat_player_id: expected one of this match's participant IDs"
                )
            elif (
                isinstance(scapegoat_player_id, str)
                and scapegoat_player_id in participant_camps_by_id
                and participant_camps_by_id[scapegoat_player_id] == winning_camp
            ):
                errors.append(
                    f"{label}.scapegoat_player_id: must come from the losing camp"
                )

        if not isinstance(match.get("notes"), str):
            errors.append(f"{label}.notes: expected string")

    return errors


def validate_repository() -> tuple[list[str], dict[str, Any]]:
    try:
        repository_data = load_repository_data()
        users = load_users()
        guilds = repository_data.get("guilds", [])
        teams = repository_data["teams"]
        players = repository_data["players"]
        matches = repository_data["matches"]
    except Exception as exc:
        return [str(exc)], {}

    usernames = {user["username"] for user in users if isinstance(user, dict) and user.get("username")}
    guild_errors, guild_ids = validate_guilds(guilds, usernames)
    team_errors, team_ids, team_members = validate_teams(teams)
    player_errors, player_ids, player_teams = validate_players(players, team_ids)
    roster_errors = validate_rosters(team_members, player_ids, player_teams)
    match_errors = validate_matches(matches, team_ids, player_ids)
    team_guild_errors = []
    for team in teams:
        guild_id = str(team.get("guild_id") or "").strip()
        team_id = str(team.get("team_id") or "").strip() or "unknown"
        if guild_id and guild_id not in guild_ids:
            team_guild_errors.append(
                f"teams[{team_id}].guild_id: unknown guild_id {guild_id!r}"
            )

    errors = [
        *guild_errors,
        *team_errors,
        *player_errors,
        *roster_errors,
        *match_errors,
        *team_guild_errors,
    ]
    data = {
        **repository_data,
        "guilds": guilds,
        "teams": teams,
        "players": players,
        "matches": matches,
    }
    return errors, data


def main() -> int:
    errors, data = validate_repository()

    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Validation passed.")
    print(f"Guilds: {len(data.get('guilds', []))}")
    print(f"Teams: {len(data['teams'])}")
    print(f"Players: {len(data['players'])}")
    print(f"Matches: {len(data['matches'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
