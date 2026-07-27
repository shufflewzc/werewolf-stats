import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from filter_player_photo_zip import (
    Player,
    apply_manual_selections,
    count_review_groups,
    list_photo_files,
    match_photos,
    read_roster_from_site,
    resolve_api_season,
    write_zip,
)


class PlayerPhotoMatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def touch_photo(self, relative_path: str) -> Path:
        path = self.folder / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        signatures = {
            ".png": b"\x89PNG\r\n\x1a\n",
            ".jpg": b"\xff\xd8\xff",
            ".jpeg": b"\xff\xd8\xff",
            ".webp": b"RIFF\x00\x00\x00\x00WEBP",
            ".gif": b"GIF89a",
        }
        path.write_bytes(signatures[path.suffix.lower()] + b"test-image")
        return path

    def test_recursively_matches_exact_name_and_ignores_unrelated_images(self):
        self.touch_photo("京城名人堂/Moony.jpg")
        self.touch_photo("其他图片/海报.png")
        players = [
            Player("player-moony-2", "Moony", team_name="京城名人堂"),
        ]

        photos = list_photo_files(self.folder, set())
        matches = match_photos(self.folder, photos, players)

        self.assertEqual(len(matches), 2)
        included = [item for item in matches if item.status == "included"]
        self.assertEqual(len(included), 1)
        self.assertEqual(included[0].player.player_id, "player-moony-2")

    def test_matches_common_filename_variants(self):
        self.touch_photo("O.TCLUB-宁自-选手头像 (1).webp")
        players = [
            Player("player-player-235", "宁自", team_name="O.TCLUB"),
        ]

        matches = match_photos(
            self.folder,
            list_photo_files(self.folder, set()),
            players,
        )

        self.assertEqual(matches[0].status, "included")
        self.assertEqual(matches[0].player.player_id, "player-player-235")

    def test_same_name_uses_team_context(self):
        self.touch_photo("甲队/小明.png")
        players = [
            Player("player-a", "小明", team_name="甲队"),
            Player("player-b", "小明", team_name="乙队"),
        ]

        matches = match_photos(
            self.folder,
            list_photo_files(self.folder, set()),
            players,
        )

        self.assertEqual(matches[0].status, "included")
        self.assertEqual(matches[0].player.player_id, "player-a")

    def test_multiple_photos_for_one_player_are_not_auto_included(self):
        self.touch_photo("Moony.jpg")
        self.touch_photo("子目录/Moony.png")
        players = [Player("player-moony-2", "Moony")]

        matches = match_photos(
            self.folder,
            list_photo_files(self.folder, set()),
            players,
        )

        self.assertEqual([item.status for item in matches], ["duplicate", "duplicate"])
        output = self.folder / "output.zip"
        self.assertEqual(write_zip(output, matches), 0)
        with ZipFile(output) as archive:
            self.assertEqual(archive.namelist(), [])

    def test_manual_selection_resolves_duplicate_and_writes_selected_photo(self):
        self.touch_photo("Moony.jpg")
        self.touch_photo("子目录/Moony.png")
        players = [Player("player-moony-2", "Moony")]
        matches = match_photos(
            self.folder,
            list_photo_files(self.folder, set()),
            players,
        )

        resolved, confirmed_count = apply_manual_selections(
            self.folder,
            matches,
            {"player-moony-2": "子目录/Moony.png"},
        )

        self.assertEqual(confirmed_count, 1)
        self.assertEqual(count_review_groups(resolved), 0)
        self.assertEqual(
            [(item.path.name, item.status) for item in resolved],
            [("Moony.jpg", "rejected"), ("Moony.png", "included")],
        )
        output = self.folder / "output.zip"
        self.assertEqual(write_zip(output, resolved), 1)
        with ZipFile(output) as archive:
            self.assertEqual(archive.namelist(), ["player-moony-2.png"])

    def test_invalid_image_is_reported_and_not_included(self):
        path = self.folder / "Moony.png"
        path.write_bytes(b"not-a-png")
        players = [Player("player-moony-2", "Moony")]

        matches = match_photos(
            self.folder,
            list_photo_files(self.folder, set()),
            players,
        )

        self.assertEqual(matches[0].status, "invalid")
        self.assertIn("扩展名不一致", matches[0].reason)

    def test_resolves_unique_short_season_name(self):
        self.assertEqual(
            resolve_api_season(
                "S2",
                ["2025广州公开赛S1", "2026广州公开赛S2"],
            ),
            "2026广州公开赛S2",
        )

    def test_reads_every_api_page(self):
        calls = []

        def fake_fetcher(_url, params):
            calls.append(params)
            if "season" not in params:
                return {
                    "scope": {
                        "filters": {
                            "seasons": [
                                {"label": "2026广州公开赛S2"},
                            ]
                        }
                    }
                }
            if params["offset"] == 0:
                return {
                    "players": [
                        {
                            "player_id": "player-a",
                            "display_name": "甲",
                            "team_name": "一队",
                            "games_played": 3,
                        }
                    ],
                    "pagination": {
                        "offset": 0,
                        "limit": 100,
                        "has_more": True,
                    },
                }
            return {
                "players": [
                    {
                        "player_id": "player-b",
                        "display_name": "乙",
                        "team_name": "二队",
                        "games_played": 2,
                    }
                ],
                "pagination": {
                    "offset": 100,
                    "limit": 100,
                    "has_more": False,
                },
            }

        players, season = read_roster_from_site(
            "https://example.com",
            "京城大师赛广州公开赛",
            "S2",
            fetcher=fake_fetcher,
        )

        self.assertEqual(season, "2026广州公开赛S2")
        self.assertEqual({player.player_id for player in players}, {"player-a", "player-b"})
        self.assertEqual(calls[-1]["offset"], 100)


if __name__ == "__main__":
    unittest.main()
