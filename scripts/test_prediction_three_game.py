from __future__ import annotations

import random
import unittest
from collections import Counter, defaultdict
from copy import deepcopy
from unittest.mock import patch

import web_app
from web.features.match_page import (
    _handle_prediction_day_scenario_admin,
    normalize_prediction_day_scenario,
    prediction_day_scenario_key,
)
from web.features.prediction_simulator import (
    SEED_COMPETITION,
    SEED_END_DATE,
    SEED_SEASON,
    build_history_model,
    draw_role_assignment,
    score_without_adjustment,
    simulate_three_game_day,
)


class ThreeGamePredictionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = web_app.load_validated_data()
        cls.jcds_competitions = {
            entry["competition_name"]
            for entry in web_app.load_series_catalog(cls.data)
            if entry["series_slug"] == "jcds"
        }
        team_lookup = {team["team_id"]: team for team in cls.data["teams"]}
        cls.roster = []
        for index, player in enumerate(cls.data["players"][:12], start=1):
            team_id = str(player.get("team_id") or "")
            cls.roster.append(
                {
                    "seat": index,
                    "player_id": player["player_id"],
                    "player_name": player.get("display_name") or player["player_id"],
                    "team_id": team_id,
                    "team_name": team_lookup.get(team_id, {}).get("name") or "未知战队",
                    "manual_total_override": None,
                }
            )

    def simulate(self, roster=None, simulations=1_000):
        return simulate_three_game_day(
            self.data,
            roster or self.roster,
            competition_name=SEED_COMPETITION,
            season_name="2026广州公开赛S2",
            played_on="2026-06-01",
            jcds_competitions=self.jcds_competitions,
            simulations=simulations,
        )

    def test_s1_golden_daily_totals_and_camp_results(self) -> None:
        seed_matches = [
            match
            for match in self.data["matches"]
            if match.get("competition_name") == SEED_COMPETITION
            and match.get("season") == SEED_SEASON
            and str(match.get("played_on") or "") <= SEED_END_DATE
            and match.get("winning_camp") in {"villagers", "werewolves"}
        ]
        self.assertEqual(len(seed_matches), 114)
        camp_counts = Counter(match["winning_camp"] for match in seed_matches)
        self.assertEqual(camp_counts["werewolves"], 75)
        self.assertEqual(camp_counts["villagers"], 39)

        daily_totals = defaultdict(float)
        for match in seed_matches:
            for participant in match.get("players", []):
                player_id = str(participant.get("player_id") or "")
                if not player_id or player_id.upper() == "NPC":
                    continue
                daily_totals[(match["played_on"], player_id)] += score_without_adjustment(participant)
        totals = list(daily_totals.values())
        self.assertEqual(len(totals), 480)
        self.assertAlmostEqual(sum(totals) / len(totals), 7.65625, places=5)
        self.assertEqual(
            [
                sum(value < 0 for value in totals),
                sum(value < 5 for value in totals),
                sum(value < 10 for value in totals),
                sum(value > 10 for value in totals),
                sum(value > 15 for value in totals),
                sum(value > 18 for value in totals),
            ],
            [37, 142, 299, 166, 45, 9],
        )

    def test_role_assignment_is_always_four_four_four(self) -> None:
        rng = random.Random(20260804)
        for _ in range(100):
            assignment = draw_role_assignment(rng)
            self.assertEqual(Counter(assignment), {"wolf": 4, "god": 4, "civilian": 4})

    def test_fixed_input_is_fully_reproducible(self) -> None:
        first = self.simulate(simulations=500)
        second = self.simulate(simulations=500)
        self.assertEqual(first, second)

    def test_manual_total_correction_does_not_change_win_probabilities(self) -> None:
        baseline = self.simulate(simulations=800)
        adjusted_roster = [dict(row) for row in self.roster]
        adjusted_roster[0]["manual_total_override"] = 2.0
        adjusted = self.simulate(adjusted_roster, simulations=800)
        baseline_by_id = {item["player_id"]: item for item in baseline["predictions"]}
        adjusted_by_id = {item["player_id"]: item for item in adjusted["predictions"]}
        target_id = adjusted_roster[0]["player_id"]
        self.assertEqual(
            baseline_by_id[target_id]["game_win_probabilities"],
            adjusted_by_id[target_id]["game_win_probabilities"],
        )
        self.assertAlmostEqual(
            float(adjusted_by_id[target_id]["expected_total"])
            - float(baseline_by_id[target_id]["expected_total"]),
            2.0,
            places=2,
        )
        for player_id in baseline_by_id:
            if player_id == target_id:
                continue
            self.assertEqual(
                baseline_by_id[player_id]["expected_total"],
                adjusted_by_id[player_id]["expected_total"],
            )

    def test_probability_ranges_and_conservation(self) -> None:
        payload = self.simulate(simulations=1_000)
        for item in payload["predictions"]:
            self.assertTrue(all(0 <= value <= 1 for value in item["game_win_probabilities"]))
            win_probabilities = item["win_count_probabilities"]
            self.assertAlmostEqual(sum(entry["probability"] for entry in win_probabilities), 1.0, places=3)
            market_by_key = {market["key"]: market for market in item["market_probabilities"]}
            for market in market_by_key.values():
                self.assertGreaterEqual(market["probability"], 0)
                self.assertLessEqual(market["probability"], 1)
                self.assertGreaterEqual(market["equality_probability"], 0)
                self.assertLessEqual(market["equality_probability"], 1)
            self.assertAlmostEqual(
                market_by_key["lt_10"]["probability"]
                + market_by_key["gt_10"]["probability"]
                + market_by_key["lt_10"]["equality_probability"],
                1.0,
                places=3,
            )

    def test_unknown_profiles_fall_back_to_population_prior(self) -> None:
        roster = [
            {
                "seat": index,
                "scenario_player_id": f"scenario-{index}",
                "player_id": "",
                "player_name": f"陌生选手{index}",
                "team_id": "",
                "team_name": f"陌生战队{index}",
                "manual_total_override": None,
            }
            for index in range(1, 13)
        ]
        payload = self.simulate(roster, simulations=300)
        self.assertTrue(all(item["model_source"] == "population_prior" for item in payload["predictions"]))
        self.assertTrue(all(not item["profile_href"] for item in payload["predictions"]))

    def test_history_excludes_prediction_day_and_future_results(self) -> None:
        baseline = build_history_model(
            self.data,
            competition_name=SEED_COMPETITION,
            prediction_date="2026-06-01",
            jcds_competitions=self.jcds_competitions,
        )
        data_with_future = deepcopy(self.data)
        future_match = deepcopy(
            next(match for match in self.data["matches"] if match.get("players"))
        )
        future_match["match_id"] = "future-prediction-leak-check"
        future_match["played_on"] = "2026-06-01"
        future_match["winning_camp"] = "werewolves"
        for participant in future_match["players"]:
            participant["points_earned"] = 999
            participant["adjustment_points"] = 0
        data_with_future["matches"].append(future_match)
        after = build_history_model(
            data_with_future,
            competition_name=SEED_COMPETITION,
            prediction_date="2026-06-01",
            jcds_competitions=self.jcds_competitions,
        )
        self.assertEqual(baseline["history_match_count"], after["history_match_count"])
        self.assertEqual(baseline["wolf_prior"], after["wolf_prior"])
        self.assertEqual(baseline["seed_market_hit_counts"], after["seed_market_hit_counts"])

    def test_scenario_normalization_keeps_metadata_separate(self) -> None:
        scenario = normalize_prediction_day_scenario(
            {
                "competition_name": SEED_COMPETITION,
                "season_name": "2026广州公开赛S2",
                "played_on": "2026-08-04",
                "published": True,
                "roster": self.roster,
            }
        )
        self.assertIsNotNone(scenario)
        self.assertEqual(len(scenario["roster"]), 12)
        self.assertNotIn("matches", scenario)

    def scenario_context(self, *, duplicate: bool = False, override: str = ""):
        form = {
            "scenario_competition": [SEED_COMPETITION],
            "scenario_season": [SEED_SEASON],
            "scenario_date": ["2026-08-04"],
        }
        for index in range(1, 13):
            form[f"scenario_player_{index}"] = ["重复选手" if duplicate else f"发布选手{index}"]
            form[f"scenario_team_{index}"] = [f"发布战队{index}"]
            form[f"scenario_override_{index}"] = [override if index == 1 else ""]
        return web_app.RequestContext(
            method="POST",
            path="/prediction-admin",
            query={},
            form=form,
            files={},
            current_user={"username": "admin", "display_name": "管理员", "role": "admin"},
            now_label="2026-08-04 12:00:00 中国时间",
        )

    def test_admin_publish_rejects_duplicate_players(self) -> None:
        statuses = []
        with patch("web.features.match_page.load_prediction_day_scenarios", return_value={}), patch(
            "web.features.match_page.save_prediction_day_scenarios"
        ) as save_mock:
            _handle_prediction_day_scenario_admin(
                self.scenario_context(duplicate=True),
                lambda status, headers: statuses.append(status),
                self.data,
                "save_day_scenario",
            )
        self.assertEqual(statuses[0], "400 Bad Request")
        save_mock.assert_not_called()

    def test_admin_publish_validates_half_point_correction(self) -> None:
        statuses = []
        with patch("web.features.match_page.load_prediction_day_scenarios", return_value={}), patch(
            "web.features.match_page.save_prediction_day_scenarios"
        ) as save_mock:
            _handle_prediction_day_scenario_admin(
                self.scenario_context(override="1.2"),
                lambda status, headers: statuses.append(status),
                self.data,
                "save_day_scenario",
            )
        self.assertEqual(statuses[0], "400 Bad Request")
        save_mock.assert_not_called()

    def test_admin_publish_saves_one_version_for_scope_and_date(self) -> None:
        statuses = []
        captured = {}

        def capture(payload):
            captured.update(payload)

        with patch("web.features.match_page.load_prediction_day_scenarios", return_value={}), patch(
            "web.features.match_page.save_prediction_day_scenarios", side_effect=capture
        ), patch("web.features.match_page.legacy.audit_action"):
            _handle_prediction_day_scenario_admin(
                self.scenario_context(override="1.5"),
                lambda status, headers: statuses.append(status),
                self.data,
                "save_day_scenario",
            )
        self.assertEqual(statuses[0], "302 Found")
        self.assertEqual(len(captured), 1)
        scenario = next(iter(captured.values()))
        self.assertTrue(scenario["published"])
        self.assertEqual(len(scenario["roster"]), 12)
        self.assertEqual(scenario["roster"][0]["manual_total_override"], 1.5)

    def test_predictions_api_prefers_published_scenario_and_keeps_legacy_fields(self) -> None:
        roster = [
            {
                "seat": index,
                "scenario_player_id": f"scenario-api-{index}",
                "player_id": "",
                "player_name": f"接口选手{index}",
                "team_id": "",
                "team_name": f"接口战队{index}",
                "manual_total_override": None,
            }
            for index in range(1, 13)
        ]
        played_on = "2026-08-04"
        scenario = normalize_prediction_day_scenario(
            {
                "competition_name": SEED_COMPETITION,
                "season_name": SEED_SEASON,
                "played_on": played_on,
                "published": True,
                "roster": roster,
            }
        )
        key = prediction_day_scenario_key(SEED_COMPETITION, SEED_SEASON, played_on)
        ctx = web_app.RequestContext(
            method="GET",
            path="/api/predictions",
            query={
                "competition": [SEED_COMPETITION],
                "season": [SEED_SEASON],
                "played_on": [played_on],
            },
            form={},
            files={},
            current_user=None,
            now_label="2026-08-04 12:00:00 中国时间",
        )
        with patch(
            "web.features.match_page.load_prediction_day_scenarios",
            return_value={key: scenario},
        ):
            payload = web_app.build_predictions_api_base_payload(ctx)
        self.assertEqual(payload["roster_source"], "published_scenario")
        self.assertEqual(payload["model_metadata"]["version"], "jcds_three_game_v1")
        self.assertEqual(len(payload["predictions"]), 12)
        item = payload["predictions"][0]
        for field in (
            "player_id",
            "player_name",
            "team_name",
            "expected_points",
            "expected_total",
            "game_win_probabilities",
            "expected_wins",
            "win_count_probabilities",
            "market_probabilities",
            "manual_override_applied",
        ):
            self.assertIn(field, item)
        self.assertEqual(len(item["game_win_probabilities"]), 3)
        self.assertEqual(len(item["market_probabilities"]), 6)


if __name__ == "__main__":
    unittest.main()
    build_history_model,
