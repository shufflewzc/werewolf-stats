from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

import competition_meta
import web_app
from web.features import competitions, match_page, player_page, team_page


COMPETITION = "测试赛事"
ENDED_SEASON = "S1"
ONGOING_SEASON = "S2"
OTHER_COMPETITION = "测试赛事二"


def _player(player_id: str, name: str, team_id: str) -> dict:
    return {
        "player_id": player_id,
        "display_name": name,
        "team_id": team_id,
        "photo": "assets/players/default-player.svg",
        "aliases": [],
        "active": True,
        "is_star_player": False,
        "joined_on": "2025-01-01",
        "notes": "",
    }


def _team(team_id: str, name: str, season: str, member_id: str) -> dict:
    return {
        "team_id": team_id,
        "name": name,
        "short_name": name,
        "logo": "assets/teams/default-team.svg",
        "competition_name": COMPETITION,
        "season_name": season,
        "members": [member_id],
    }


def _match(match_id: str, season: str, player_id: str, team_id: str, points: float, played_on: str) -> dict:
    return {
        "match_id": match_id,
        "competition_name": COMPETITION,
        "season": season,
        "stage": "regular_season",
        "round": 1,
        "game_no": 1,
        "played_on": played_on,
        "table_label": "1号房",
        "format": "预女猎白",
        "duration_minutes": 45,
        "winning_camp": "villagers",
        "notes": "",
        "players": [
            {
                "seat": 1,
                "player_id": player_id,
                "team_id": team_id,
                "role": "预言家",
                "camp": "villagers",
                "result": "win",
                "points_earned": points,
                "stance_result": "correct",
                "notes": "",
            }
        ],
    }


def _dimension_row(
    player_id: str,
    team_id: str,
    season: str,
    played_on: str,
    points: float,
) -> dict:
    return {
        "competition_name": COMPETITION,
        "season_name": season,
        "played_on": played_on,
        "player_id": player_id,
        "team_id": team_id,
        "seat": 1,
        "daily_points": points,
        "games_played": 1,
        "wins": 1,
        "villager_games": 1,
        "villager_wins": 1,
        "werewolf_games": 0,
        "werewolf_wins": 0,
        "vote_count": 1,
        "vote_wolf_count": 1,
        "mvp_count": 0,
        "svp_count": 0,
        "scapegoat_count": 0,
    }


def sample_data() -> dict:
    return {
        "players": [
            _player("player-s1", "历史选手", "team-s1"),
            _player("player-s2", "当前选手", "team-s2"),
        ],
        "teams": [
            _team("team-s1", "S1 战队", ENDED_SEASON, "player-s1"),
            _team("team-s2", "S2 战队", ONGOING_SEASON, "player-s2"),
        ],
        "matches": [
            _match("match-s1", ENDED_SEASON, "player-s1", "team-s1", 75, "2025-08-01"),
            _match("match-s2", ONGOING_SEASON, "player-s2", "team-s2", 8, "2026-08-01"),
        ],
        "season_player_dimension_stats": [],
        "season_team_dimension_stats": [],
    }


def series_catalog() -> list[dict]:
    entry = competition_meta.normalize_series_catalog_entry(
        {
            "competition_name": COMPETITION,
            "region_name": "广州",
            "series_name": "测试系列赛",
            "series_code": "TEST",
            "series_slug": "test-series",
            "active": True,
        }
    )
    assert entry is not None
    return [entry]


def season_catalog(series: list[dict]) -> list[dict]:
    rows = []
    for season, start_at, end_at in [
        (ENDED_SEASON, "2025-01-01", "2025-12-31"),
        (ONGOING_SEASON, "2026-01-01", "2026-12-31"),
    ]:
        entry = competition_meta.normalize_season_catalog_entry(
            {
                "competition_name": COMPETITION,
                "series_slug": "test-series",
                "series_name": "测试系列赛",
                "series_code": "TEST",
                "season_name": season,
                "start_at": start_at,
                "end_at": end_at,
            },
            series,
        )
        assert entry is not None
        rows.append(entry)
    return rows


class PlayerScopeContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = sample_data()
        self.series = series_catalog()
        self.seasons = season_catalog(self.series)
        self.patchers = [
            patch.object(player_page, "load_validated_data", return_value=self.data),
            patch.object(player_page, "load_users", return_value=[]),
            patch.object(match_page, "load_validated_data", return_value=self.data),
            patch.object(team_page, "load_validated_data", return_value=self.data),
            patch.object(competitions, "load_validated_data", return_value=self.data),
            patch.object(competitions, "load_series_catalog", return_value=self.series),
            patch.object(web_app, "load_validated_data", return_value=self.data),
            patch.object(match_page, "build_match_score_predictions", return_value=[]),
            patch.object(competition_meta, "load_series_catalog", return_value=self.series),
            patch.object(competition_meta, "load_season_catalog", return_value=self.seasons),
            patch.object(web_app, "load_series_catalog", return_value=self.series),
            patch.object(web_app, "load_season_catalog", return_value=self.seasons),
            patch.object(web_app, "load_meta_value", return_value=None),
            patch.object(web_app, "get_database_cache_signature", return_value=None),
            patch.object(web_app, "request_rate_limited", return_value=(False, 0)),
            patch.object(web_app, "enqueue_access_log"),
        ]
        for patcher in self.patchers:
            patcher.start()
        web_app.invalidate_public_api_cache()

    def tearDown(self) -> None:
        web_app.invalidate_public_api_cache()
        for patcher in reversed(self.patchers):
            patcher.stop()

    @staticmethod
    def context(path: str, **query: str) -> web_app.RequestContext:
        return web_app.RequestContext(
            method="GET",
            path=path,
            query={key: [value] for key, value in query.items()},
            form={},
            files={},
            current_user=None,
            now_label="now",
        )

    @staticmethod
    def call(handler, ctx: web_app.RequestContext, *args: str) -> tuple[str, dict]:
        response: dict[str, object] = {}

        def start_response(status, headers):
            response["status"] = status
            response["headers"] = headers

        body = web_app.validate_public_api_scope_request(ctx, start_response)
        if body is None:
            body = handler(ctx, start_response, *args)
        return str(response["status"]), json.loads(body[0])

    @staticmethod
    def call_wsgi(path: str, **query: str) -> tuple[str, dict]:
        response: dict[str, object] = {}

        def start_response(status, headers, exc_info=None):
            response["status"] = status
            response["headers"] = headers

        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": path,
            "QUERY_STRING": urlencode(query),
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_USER_AGENT": "player-scope-contract-test",
            "HTTP_COOKIE": "",
            "wsgi.input": io.BytesIO(b""),
            "CONTENT_LENGTH": "0",
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
        }
        body = b"".join(web_app.app(environ, start_response))
        return str(response["status"]), json.loads(body)

    def assert_scope(self, payload: dict, season: str) -> None:
        self.assertEqual(
            {
                "competition": payload["scope"].get("competition"),
                "season": payload["scope"].get("season"),
            },
            {"competition": COMPETITION, "season": season},
        )

    def test_strict_players_scope_requires_both_competition_and_season(self) -> None:
        incomplete_queries = [
            {"scope_required": "1"},
            {"scope_required": "1", "competition": COMPETITION},
            {"scope_required": "1", "season": ENDED_SEASON},
        ]
        for query in incomplete_queries:
            with self.subTest(query=query):
                status, payload = self.call(
                    web_app.handle_players_api,
                    self.context("/api/players", **query),
                )
                self.assertEqual(status, "400 Bad Request")
                self.assertEqual(payload["code"], "SCOPE_REQUIRED")
                self.assertEqual(
                    payload["requested_scope"],
                    {
                        "competition": query.get("competition", ""),
                        "season": query.get("season", ""),
                    },
                )
                self.assertNotIn("players", payload)

    def test_wsgi_dispatcher_applies_scope_guard_before_players_handler(self) -> None:
        status, payload = self.call_wsgi(
            "/api/players",
            scope_required="1",
            competition=COMPETITION,
        )
        self.assertEqual(status, "400 Bad Request")
        self.assertEqual(payload["code"], "SCOPE_REQUIRED")
        self.assertEqual(
            payload["requested_scope"],
            {"competition": COMPETITION, "season": ""},
        )

    def test_strict_player_detail_scope_requires_both_values(self) -> None:
        status, payload = self.call(
            web_app.handle_player_api,
            self.context(
                "/api/players/player-s1",
                scope_required="1",
                competition=COMPETITION,
            ),
            "player-s1",
        )
        self.assertEqual(status, "400 Bad Request")
        self.assertEqual(payload["code"], "SCOPE_REQUIRED")
        self.assertEqual(
            payload["requested_scope"],
            {"competition": COMPETITION, "season": ""},
        )
        self.assertNotIn("player", payload)

    def test_unknown_competition_or_season_is_not_substituted(self) -> None:
        invalid_queries = [
            {"competition": "不存在的赛事", "season": ENDED_SEASON},
            {"competition": COMPETITION, "season": "S404"},
        ]
        for query in invalid_queries:
            with self.subTest(query=query):
                status, payload = self.call(
                    web_app.handle_players_api,
                    self.context("/api/players", scope_required="1", **query),
                )
                self.assertEqual(status, "404 Not Found")
                self.assertEqual(payload["code"], "SCOPE_NOT_FOUND")
                self.assertEqual(payload["requested_scope"], query)
                self.assertNotIn("players", payload)

    def test_ended_s1_list_keeps_75_points_and_exact_scope(self) -> None:
        status, payload = self.call(
            web_app.handle_players_api,
            self.context(
                "/api/players",
                scope_required="1",
                competition=COMPETITION,
                season=ENDED_SEASON,
            ),
        )
        self.assertEqual(status, "200 OK")
        self.assert_scope(payload, ENDED_SEASON)
        self.assertEqual(
            [(row["player_id"], row["points_total"], row["games_played"]) for row in payload["players"]],
            [("player-s1", "75.00", 1)],
        )
        self.assertIn("season=S1", payload["players"][0]["href"])

    def test_ongoing_s2_list_still_returns_8_points(self) -> None:
        status, payload = self.call(
            web_app.handle_players_api,
            self.context(
                "/api/players",
                scope_required="1",
                competition=COMPETITION,
                season=ONGOING_SEASON,
            ),
        )
        self.assertEqual(status, "200 OK")
        self.assert_scope(payload, ONGOING_SEASON)
        self.assertEqual(
            [(row["player_id"], row["points_total"], row["games_played"]) for row in payload["players"]],
            [("player-s2", "8.00", 1)],
        )

    def test_equal_points_keep_win_rate_ranking_before_average_points(self) -> None:
        self.data["players"].extend(
            [
                _player("player-win-rate", "胜率优先", "team-win-rate"),
                _player("player-average", "场均更高", "team-average"),
            ]
        )
        self.data["teams"].extend(
            [
                _team("team-win-rate", "胜率优先队", ENDED_SEASON, "player-win-rate"),
                _team("team-average", "场均更高队", ENDED_SEASON, "player-average"),
            ]
        )
        first_win = _match(
            "match-win-rate-1",
            ENDED_SEASON,
            "player-win-rate",
            "team-win-rate",
            5,
            "2025-08-02",
        )
        second_win = _match(
            "match-win-rate-2",
            ENDED_SEASON,
            "player-win-rate",
            "team-win-rate",
            5,
            "2025-08-03",
        )
        high_average_loss = _match(
            "match-average-1",
            ENDED_SEASON,
            "player-average",
            "team-average",
            10,
            "2025-08-04",
        )
        high_average_loss["winning_camp"] = "werewolves"
        high_average_loss["players"][0]["result"] = "loss"
        self.data["matches"].extend(
            [first_win, second_win, high_average_loss]
        )

        ctx = self.context(
            "/api/players",
            scope_required="1",
            competition=COMPETITION,
            season=ENDED_SEASON,
        )
        list_status, list_payload = self.call(web_app.handle_players_api, ctx)
        dashboard_status, dashboard_payload = self.call(
            web_app.handle_dashboard_api,
            self.context(
                "/api/dashboard",
                scope_required="1",
                competition=COMPETITION,
                season=ENDED_SEASON,
            ),
        )

        self.assertEqual(list_status, "200 OK")
        self.assertEqual(dashboard_status, "200 OK")
        list_rows = {
            row["player_id"]: row
            for row in list_payload["players"]
            if row["player_id"] in {"player-win-rate", "player-average"}
        }
        dashboard_rows = {
            row["player_id"]: row
            for row in dashboard_payload["leaderboards"]["players"]
            if row["player_id"] in {"player-win-rate", "player-average"}
        }
        self.assertEqual(list_rows["player-win-rate"]["points_total"], "10.00")
        self.assertEqual(list_rows["player-average"]["points_total"], "10.00")
        self.assertEqual(list_rows["player-win-rate"]["win_rate"], "100.0%")
        self.assertEqual(list_rows["player-average"]["win_rate"], "0.0%")
        self.assertEqual(list_rows["player-win-rate"]["average_points"], "5.00")
        self.assertEqual(list_rows["player-average"]["average_points"], "10.00")
        self.assertLess(
            list_rows["player-win-rate"]["rank"],
            list_rows["player-average"]["rank"],
        )
        self.assertEqual(
            list_rows["player-win-rate"]["rank"],
            dashboard_rows["player-win-rate"]["rank"],
        )
        self.assertEqual(
            list_rows["player-average"]["rank"],
            dashboard_rows["player-average"]["rank"],
        )
        for player_id in ("player-win-rate", "player-average"):
            detail_status, detail_payload = self.call(
                web_app.handle_player_api,
                self.context(
                    f"/api/players/{player_id}",
                    scope_required="1",
                    competition=COMPETITION,
                    season=ENDED_SEASON,
                ),
                player_id,
            )
            self.assertEqual(detail_status, "200 OK")
            metrics = {
                metric["label"]: metric["value"]
                for metric in detail_payload["metrics"]
            }
            self.assertEqual(
                metrics["排名"],
                f"#{list_rows[player_id]['rank']}",
            )

    def test_explicit_scope_without_marker_does_not_return_zero_game_players(self) -> None:
        self.data["matches"] = [
            match for match in self.data["matches"] if match["season"] != ONGOING_SEASON
        ]
        status, payload = self.call(
            web_app.handle_players_api,
            self.context(
                "/api/players",
                competition=COMPETITION,
                season=ONGOING_SEASON,
            ),
        )
        self.assertEqual(status, "200 OK")
        self.assert_scope(payload, ONGOING_SEASON)
        self.assertEqual(payload["players"], [])

    def test_explicit_scope_without_marker_does_not_return_zero_game_teams(self) -> None:
        self.data["matches"] = [
            match for match in self.data["matches"] if match["season"] != ONGOING_SEASON
        ]
        status, payload = self.call(
            web_app.handle_teams_api,
            self.context(
                "/api/teams",
                competition=COMPETITION,
                season=ONGOING_SEASON,
            ),
        )
        self.assertEqual(status, "200 OK")
        self.assert_scope(payload, ONGOING_SEASON)
        self.assertEqual(payload["teams"], [])

    def test_ended_s1_detail_keeps_metrics_and_match_history(self) -> None:
        status, payload = self.call(
            web_app.handle_player_api,
            self.context(
                "/api/players/player-s1",
                scope_required="1",
                competition=COMPETITION,
                season=ENDED_SEASON,
                strict_player_id="1",
            ),
            "player-s1",
        )
        self.assertEqual(status, "200 OK")
        self.assert_scope(payload, ENDED_SEASON)
        metrics = {item["label"]: item["value"] for item in payload["metrics"]}
        self.assertEqual(metrics["总积分"], "75.00")
        self.assertEqual(metrics["出赛局数"], "1")
        self.assertEqual([row["match_id"] for row in payload["recent_matches"]], ["match-s1"])
        self.assertEqual({row["season"] for row in payload["history"]}, {ENDED_SEASON})
        self.assertIn("season=S1", payload["actions"]["players_href"])

    def test_dimension_season_cannot_override_strict_player_scope(self) -> None:
        self.data["season_player_dimension_stats"] = [
            _dimension_row("player-s1", "team-s1", ENDED_SEASON, "2025-08-01", 75),
            _dimension_row("player-s1", "team-s2", ONGOING_SEASON, "2026-08-01", 8),
        ]
        status, payload = self.call(
            web_app.handle_player_api,
            self.context(
                "/api/players/player-s1",
                scope_required="1",
                competition=COMPETITION,
                season=ENDED_SEASON,
                dimension_season=ONGOING_SEASON,
            ),
            "player-s1",
        )
        self.assertEqual(status, "200 OK")
        self.assert_scope(payload, ENDED_SEASON)
        self.assertTrue(payload["dimension"]["available"])
        self.assertEqual(payload["dimension"]["selected_season"], ENDED_SEASON)
        self.assertEqual(payload["dimension"]["available_seasons"], [ENDED_SEASON])
        self.assertEqual(
            {row["played_on"] for row in payload["dimension"]["history"]},
            {"2025-08-01"},
        )

    def test_missing_current_scope_dimension_does_not_fallback_to_other_season(self) -> None:
        self.data["season_player_dimension_stats"] = [
            _dimension_row("player-s2", "team-s1", ENDED_SEASON, "2025-08-01", 75),
        ]
        status, payload = self.call(
            web_app.handle_player_api,
            self.context(
                "/api/players/player-s2",
                scope_required="1",
                competition=COMPETITION,
                season=ONGOING_SEASON,
                dimension_season=ENDED_SEASON,
            ),
            "player-s2",
        )
        self.assertEqual(status, "200 OK")
        self.assert_scope(payload, ONGOING_SEASON)
        self.assertFalse(payload["dimension"]["available"])
        self.assertEqual(payload["dimension"]["selected_season"], ONGOING_SEASON)
        self.assertEqual(payload["dimension"]["available_seasons"], [])

    def test_player_outside_requested_scope_is_entity_404_not_zero_score(self) -> None:
        status, payload = self.call(
            web_app.handle_player_api,
            self.context(
                "/api/players/player-s1",
                scope_required="1",
                competition=COMPETITION,
                season=ONGOING_SEASON,
                strict_player_id="1",
            ),
            "player-s1",
        )
        self.assertEqual(status, "404 Not Found")
        self.assertEqual(payload["code"], "PLAYER_NOT_FOUND")
        self.assertEqual(
            payload["requested_scope"],
            {"competition": COMPETITION, "season": ONGOING_SEASON},
        )
        self.assertNotIn("metrics", payload)

    def test_current_team_scope_cannot_replace_actual_player_participation(self) -> None:
        historical_player = next(
            player for player in self.data["players"] if player["player_id"] == "player-s1"
        )
        historical_player["team_id"] = "team-s2"
        status, payload = self.call(
            web_app.handle_player_api,
            self.context(
                "/api/players/player-s1",
                scope_required="1",
                competition=COMPETITION,
                season=ONGOING_SEASON,
                strict_player_id="1",
            ),
            "player-s1",
        )
        self.assertEqual(status, "404 Not Found")
        self.assertEqual(payload["code"], "PLAYER_NOT_FOUND")
        self.assertEqual(
            payload["requested_scope"],
            {"competition": COMPETITION, "season": ONGOING_SEASON},
        )
        self.assertNotIn("metrics", payload)

    def test_scope_required_uses_url_player_id_without_same_name_rewrite(self) -> None:
        current_player = next(
            player for player in self.data["players"] if player["player_id"] == "player-s2"
        )
        current_player["display_name"] = "历史选手"
        strict_status, strict_payload = self.call(
            web_app.handle_player_api,
            self.context(
                "/api/players/player-s1",
                scope_required="1",
                competition=COMPETITION,
                season=ONGOING_SEASON,
            ),
            "player-s1",
        )
        self.assertEqual(strict_status, "404 Not Found")
        self.assertEqual(strict_payload["code"], "PLAYER_NOT_FOUND")

        legacy_status, legacy_payload = self.call(
            web_app.handle_player_api,
            self.context(
                "/api/players/player-s1",
                competition=COMPETITION,
                season=ONGOING_SEASON,
            ),
            "player-s1",
        )
        self.assertEqual(legacy_status, "200 OK")
        self.assertEqual(legacy_payload["player"]["player_id"], "player-s2")

    def test_team_outside_requested_scope_is_entity_404_not_scope_mismatch(self) -> None:
        status, payload = self.call(
            web_app.handle_team_api,
            self.context(
                "/api/teams/team-s1",
                scope_required="1",
                competition=COMPETITION,
                season=ONGOING_SEASON,
            ),
            "team-s1",
        )
        self.assertEqual(status, "404 Not Found")
        self.assertEqual(payload["code"], "TEAM_NOT_FOUND")
        self.assertEqual(
            payload["requested_scope"],
            {"competition": COMPETITION, "season": ONGOING_SEASON},
        )
        self.assertNotIn("resource_scope", payload)

    def test_strict_series_payload_filters_other_competitions_in_same_series(self) -> None:
        other_series = competition_meta.normalize_series_catalog_entry(
            {
                "competition_name": OTHER_COMPETITION,
                "region_name": "深圳",
                "series_name": "测试系列赛",
                "series_code": "TEST",
                "series_slug": "test-series",
                "active": True,
            }
        )
        self.assertIsNotNone(other_series)
        self.series.append(other_series)
        other_season = competition_meta.normalize_season_catalog_entry(
            {
                "competition_name": OTHER_COMPETITION,
                "series_slug": "test-series",
                "series_name": "测试系列赛",
                "series_code": "TEST",
                "season_name": ENDED_SEASON,
                "start_at": "2025-01-01",
                "end_at": "2025-12-31",
            },
            self.series,
        )
        self.assertIsNotNone(other_season)
        self.seasons.append(other_season)
        other_player = _player("player-other", "其他赛事选手", "team-other")
        other_team = _team("team-other", "其他赛事战队", ENDED_SEASON, "player-other")
        other_team["competition_name"] = OTHER_COMPETITION
        other_match = _match(
            "match-other",
            ENDED_SEASON,
            "player-other",
            "team-other",
            99,
            "2025-09-01",
        )
        other_match["competition_name"] = OTHER_COMPETITION
        self.data["players"].append(other_player)
        self.data["teams"].append(other_team)
        self.data["matches"].append(other_match)

        strict_status, strict_payload = self.call(
            web_app.handle_series_api,
            self.context(
                "/api/series/test-series",
                scope_required="1",
                competition=COMPETITION,
                season=ENDED_SEASON,
            ),
            "test-series",
        )
        self.assertEqual(strict_status, "200 OK")
        self.assert_scope(strict_payload, ENDED_SEASON)
        self.assertEqual(
            {card["competition_name"] for card in strict_payload["cards"]},
            {COMPETITION},
        )
        self.assertEqual(strict_payload["hero"]["latest_played_on"], "2025-08-01")

        legacy_status, legacy_payload = self.call(
            web_app.handle_series_api,
            self.context("/api/series/test-series"),
            "test-series",
        )
        self.assertEqual(legacy_status, "200 OK")
        self.assertEqual(
            {card["competition_name"] for card in legacy_payload["cards"]},
            {COMPETITION, OTHER_COMPETITION},
        )

    def test_prediction_roster_explicit_empty_season_does_not_fallback(self) -> None:
        incomplete_status, incomplete_payload = self.call(
            web_app.handle_prediction_roster_search_api,
            self.context(
                "/api/prediction-roster-search",
                scope_required="1",
                competition=COMPETITION,
            ),
        )
        self.assertEqual(incomplete_status, "400 Bad Request")
        self.assertEqual(incomplete_payload["code"], "SCOPE_REQUIRED")

        self.data["matches"] = [
            match
            for match in self.data["matches"]
            if str(match.get("season") or "") != ONGOING_SEASON
        ]
        ctx = self.context(
            "/api/prediction-roster-search",
            competition=COMPETITION,
            season=ONGOING_SEASON,
        )
        ctx.current_user = {"username": "manager", "role": "admin"}
        with patch.object(web_app, "can_manage_matches", return_value=True):
            status, payload = self.call(
                web_app.handle_prediction_roster_search_api,
                ctx,
            )
        self.assertEqual(status, "200 OK")
        self.assert_scope(payload, ONGOING_SEASON)
        self.assertEqual(payload["players"], [])
        self.assertEqual(payload["teams"], [])

    def test_match_bound_to_s1_rejects_s2_scope_with_409(self) -> None:
        status, payload = self.call(
            web_app.handle_match_api,
            self.context(
                "/api/matches/match-s1",
                scope_required="1",
                competition=COMPETITION,
                season=ONGOING_SEASON,
            ),
            "match-s1",
        )
        self.assertEqual(status, "409 Conflict")
        self.assertEqual(payload["code"], "SCOPE_MISMATCH")
        self.assertEqual(
            payload["requested_scope"],
            {"competition": COMPETITION, "season": ONGOING_SEASON},
        )
        self.assertEqual(
            payload["resource_scope"],
            {"competition": COMPETITION, "season": ENDED_SEASON},
        )

    def test_match_success_echoes_exact_resource_scope(self) -> None:
        status, payload = self.call(
            web_app.handle_match_api,
            self.context(
                "/api/matches/match-s1",
                scope_required="1",
                competition=COMPETITION,
                season=ENDED_SEASON,
            ),
            "match-s1",
        )
        self.assertEqual(status, "200 OK")
        self.assert_scope(payload, ENDED_SEASON)
        self.assertEqual(payload["match"]["match_id"], "match-s1")

    def test_player_share_scene_is_deterministic_and_compact(self) -> None:
        first = web_app.build_player_share_scene(
            "player-s1",
            COMPETITION,
            ENDED_SEASON,
        )
        second = web_app.build_player_share_scene(
            "player-s1",
            COMPETITION,
            ENDED_SEASON,
        )
        self.assertEqual(first, second)
        self.assertRegex(first, r"^p1:[0-9a-f]{24}$")
        self.assertLessEqual(len(first), 32)
        self.assertNotEqual(
            first,
            web_app.build_player_share_scene(
                "player-s1",
                COMPETITION,
                ONGOING_SEASON,
            ),
        )

    def test_player_share_entry_keeps_s1_scope_even_after_later_s2_match(self) -> None:
        self.data["matches"].append(
            _match(
                "match-s1-player-later-s2",
                ONGOING_SEASON,
                "player-s1",
                "team-s2",
                9,
                "2026-09-01",
            )
        )
        scene = web_app.build_player_share_scene(
            "player-s1",
            COMPETITION,
            ENDED_SEASON,
        )

        status, payload = self.call(
            web_app.handle_miniprogram_share_entry,
            self.context("/api/miniprogram/share-entry", scene=scene),
        )

        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["target"], "player")
        self.assertEqual(payload["player_id"], "player-s1")
        self.assert_scope(payload, ENDED_SEASON)

    def test_player_share_code_requires_complete_scope(self) -> None:
        status, payload = self.call(
            web_app.handle_miniprogram_share_code,
            self.context(
                "/api/miniprogram/share-code",
                share_type="player",
                player_id="player-s1",
                competition=COMPETITION,
            ),
        )

        self.assertEqual(status, "400 Bad Request")
        self.assertEqual(payload["code"], "SCOPE_REQUIRED")
        self.assertEqual(
            payload["requested_scope"],
            {"competition": COMPETITION, "season": ""},
        )

    def test_player_share_code_rejects_player_outside_requested_scope(self) -> None:
        status, payload = self.call(
            web_app.handle_miniprogram_share_code,
            self.context(
                "/api/miniprogram/share-code",
                share_type="player",
                player_id="player-s1",
                competition=COMPETITION,
                season=ONGOING_SEASON,
            ),
        )

        self.assertEqual(status, "404 Not Found")
        self.assertEqual(payload["code"], "PLAYER_NOT_FOUND")
        self.assertEqual(
            payload["requested_scope"],
            {"competition": COMPETITION, "season": ONGOING_SEASON},
        )

    def test_player_share_scene_collision_never_generates_or_resolves(self) -> None:
        scene = web_app.build_player_share_scene(
            "player-s1",
            COMPETITION,
            ENDED_SEASON,
        )
        exact_target = {
            "scene": scene,
            "player_id": "player-s1",
            "competition": COMPETITION,
            "season": ENDED_SEASON,
            "region": "广州",
            "series": "test-series",
            "seriesName": "测试系列赛",
        }
        colliding_target = {
            **exact_target,
            "player_id": "player-collision",
        }
        with patch.object(
            web_app,
            "list_player_share_targets",
            return_value=[exact_target, colliding_target],
        ), patch.object(
            web_app,
            "request_wechat_miniprogram_share_code",
        ) as request_mock:
            self.assertIsNone(web_app.resolve_player_share_scene(scene, self.data))

            code_status, code_payload = self.call(
                web_app.handle_miniprogram_share_code,
                self.context(
                    "/api/miniprogram/share-code",
                    share_type="player",
                    player_id="player-s1",
                    competition=COMPETITION,
                    season=ENDED_SEASON,
                ),
            )
            entry_status, entry_payload = self.call(
                web_app.handle_miniprogram_share_entry,
                self.context("/api/miniprogram/share-entry", scene=scene),
            )

        self.assertEqual(code_status, "409 Conflict")
        self.assertEqual(code_payload["code"], "SHARE_SCENE_CONFLICT")
        self.assertEqual(entry_status, "404 Not Found")
        self.assertEqual(entry_payload["code"], "SHARE_ENTRY_NOT_FOUND")
        request_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
