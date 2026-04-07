#!/usr/bin/env python3

from __future__ import annotations

import re
import sys
from datetime import date
from typing import Any

from sqlite_store import load_repository_data

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
VALID_STAGES = {"regular_season", "playoffs", "finals", "showmatch"}
VALID_CAMPS = {"villagers", "werewolves", "third_party"}
VALID_WINNING_CAMPS = {*VALID_CAMPS, "draw"}
VALID_RESULTS = {"win", "loss", "draw"}
VALID_STANCE_PICKS = {*VALID_CAMPS, "none"}


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
        "captain_player_id",
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

        if not isinstance(team.get("notes"), str):
            errors.append(f"{label}.notes: expected string")

    return errors, team_ids, team_members


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
    if winning_camp == "draw":
        return "draw"
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
        "played_on",
        "table_label",
        "format",
        "duration_minutes",
        "winning_camp",
        "players",
        "notes",
    }
    required_player_keys = {
        "player_id",
        "team_id",
        "seat",
        "role",
        "camp",
        "survived",
        "result",
        "points_earned",
        "points_available",
        "stance_pick",
        "stance_correct",
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

        errors.extend(validate_iso_date(match.get("played_on"), f"{label}.played_on"))
        errors.extend(
            validate_non_empty_string(match.get("table_label"), f"{label}.table_label")
        )
        errors.extend(validate_non_empty_string(match.get("format"), f"{label}.format"))

        winning_camp = match.get("winning_camp")
        if winning_camp not in VALID_WINNING_CAMPS:
            errors.append(
                f"{label}.winning_camp: expected one of {sorted(VALID_WINNING_CAMPS)}"
            )

        duration_minutes = match.get("duration_minutes")
        if not isinstance(duration_minutes, int) or isinstance(duration_minutes, bool):
            errors.append(f"{label}.duration_minutes: expected integer")
        elif duration_minutes < 1:
            errors.append(f"{label}.duration_minutes: must be >= 1")

        participants = match.get("players")
        if not isinstance(participants, list):
            errors.append(f"{label}.players: expected array")
        elif not participants:
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

                errors.extend(
                    validate_non_empty_string(participant.get("role"), f"{participant_label}.role")
                )

                camp = participant.get("camp")
                if camp not in VALID_CAMPS:
                    errors.append(
                        f"{participant_label}.camp: expected one of {sorted(VALID_CAMPS)}"
                    )

                if not isinstance(participant.get("survived"), bool):
                    errors.append(f"{participant_label}.survived: expected boolean")

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
                elif points_earned < 0:
                    errors.append(f"{participant_label}.points_earned: must be >= 0")

                points_available = participant.get("points_available")
                if not is_number(points_available):
                    errors.append(f"{participant_label}.points_available: expected number")
                elif points_available <= 0:
                    errors.append(f"{participant_label}.points_available: must be > 0")
                elif is_number(points_earned) and points_earned > points_available:
                    errors.append(
                        f"{participant_label}.points_earned: cannot exceed points_available"
                    )

                stance_pick = participant.get("stance_pick")
                if stance_pick not in VALID_STANCE_PICKS:
                    errors.append(
                        f"{participant_label}.stance_pick: expected one of {sorted(VALID_STANCE_PICKS)}"
                    )

                stance_correct = participant.get("stance_correct")
                if not isinstance(stance_correct, bool):
                    errors.append(f"{participant_label}.stance_correct: expected boolean")
                elif stance_pick == "none" and stance_correct:
                    errors.append(
                        f"{participant_label}.stance_correct: cannot be true when stance_pick is 'none'"
                    )

                if not isinstance(participant.get("notes"), str):
                    errors.append(f"{participant_label}.notes: expected string")

        if not isinstance(match.get("notes"), str):
            errors.append(f"{label}.notes: expected string")

    return errors


def validate_repository() -> tuple[list[str], dict[str, Any]]:
    try:
        data = load_repository_data()
        teams = data["teams"]
        players = data["players"]
        matches = data["matches"]
    except Exception as exc:
        return [str(exc)], {}

    team_errors, team_ids, team_members = validate_teams(teams)
    player_errors, player_ids, player_teams = validate_players(players, team_ids)
    roster_errors = validate_rosters(team_members, player_ids, player_teams)
    match_errors = validate_matches(matches, team_ids, player_ids)

    errors = [*team_errors, *player_errors, *roster_errors, *match_errors]
    data = {
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
    print(f"Teams: {len(data['teams'])}")
    print(f"Players: {len(data['players'])}")
    print(f"Matches: {len(data['matches'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
