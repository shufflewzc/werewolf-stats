import unittest

from power_rating import (
    apply_power_rating_override,
    calculate_power_ratings,
    save_power_rating_override,
)


class PowerRatingTests(unittest.TestCase):
    def test_calculates_relative_grades(self):
        rows = [
            {"id": "top", "points": 30, "average": 6, "win_rate": 0.7, "games": 5},
            {"id": "middle", "points": 15, "average": 3, "win_rate": 0.5, "games": 5},
            {"id": "bottom", "points": 2, "average": 1, "win_rate": 0.2, "games": 5},
        ]
        ratings = calculate_power_ratings(
            rows,
            id_key="id",
            total_key="points",
            efficiency_key="average",
            win_rate_key="win_rate",
            games_key="games",
        )
        self.assertEqual(ratings["top"]["grade"], "S")
        self.assertEqual(ratings["bottom"]["grade"], "D")

    def test_manual_override_and_restore_auto(self):
        storage = {}
        load = storage.get
        save = storage.__setitem__
        params = {
            "entity_type": "player",
            "entity_id": "p1",
            "competition_name": "赛事",
            "season_name": "S1",
            "updated_by": "admin",
            "updated_at": "now",
        }
        save_power_rating_override(load, save, grade="A", **params)
        rating = apply_power_rating_override(
            {"grade": "C", "auto_grade": "C", "score": 50, "source": "auto"},
            __import__("power_rating").parse_power_rating_overrides(storage["power_rating_overrides"]),
            entity_type="player",
            entity_id="p1",
            competition_name="赛事",
            season_name="S1",
        )
        self.assertEqual(rating["grade"], "A")
        save_power_rating_override(load, save, grade="", **params)
        self.assertEqual(__import__("power_rating").parse_power_rating_overrides(storage["power_rating_overrides"]), [])


if __name__ == "__main__":
    unittest.main()
