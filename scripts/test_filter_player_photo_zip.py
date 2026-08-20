import tempfile
import json
import unittest
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from filter_player_photo_zip import (
    MAX_UPLOAD_BYTES,
    CompressionResult,
    Image as PILImage,
    Player,
    ManualSelections,
    apply_manual_selections,
    count_review_groups,
    list_photo_files,
    load_manual_selections,
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

    def test_recursively_scans_supported_formats_and_skips_hidden_folders(self):
        expected = {
            "一层/二层/a.png",
            "一层/二层/b.jpg",
            "一层/二层/c.webp",
            "一层/二层/d.gif",
        }
        for relative_path in expected:
            self.touch_photo(relative_path)
        self.touch_photo(".hidden/secret.png")

        photos = list_photo_files(self.folder, set())

        self.assertEqual(
            {str(path.relative_to(self.folder.resolve())) for path in photos},
            expected,
        )

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

    def test_manual_selection_assigns_unmatched_nested_photo(self):
        self.touch_photo("待处理/深层/portrait.png")
        players = [Player("player-a", "甲", team_name="一队")]
        matches = match_photos(
            self.folder,
            list_photo_files(self.folder, set()),
            players,
        )
        self.assertEqual(matches[0].status, "unmatched")

        resolved, handled_count = apply_manual_selections(
            self.folder,
            matches,
            ManualSelections(
                assignments={"player-a": "待处理/深层/portrait.png"},
            ),
            players,
        )

        self.assertEqual(handled_count, 1)
        self.assertEqual(resolved[0].status, "included")
        self.assertEqual(resolved[0].player.player_id, "player-a")
        self.assertEqual(resolved[0].method, "App 内人工指定")

    def test_manual_selection_overrides_auto_match_and_rejects_old_photo(self):
        self.touch_photo("甲.png")
        self.touch_photo("correct.png")
        players = [Player("player-a", "甲")]
        matches = match_photos(
            self.folder,
            list_photo_files(self.folder, set()),
            players,
        )

        resolved, _handled_count = apply_manual_selections(
            self.folder,
            matches,
            ManualSelections(assignments={"player-a": "correct.png"}),
            players,
        )

        by_source = {
            str(item.path.relative_to(self.folder.resolve())): item for item in resolved
        }
        self.assertEqual(by_source["correct.png"].status, "included")
        self.assertEqual(by_source["甲.png"].status, "rejected")

    def test_manual_rejection_excludes_auto_match(self):
        self.touch_photo("甲.png")
        players = [Player("player-a", "甲")]
        matches = match_photos(
            self.folder,
            list_photo_files(self.folder, set()),
            players,
        )

        resolved, handled_count = apply_manual_selections(
            self.folder,
            matches,
            ManualSelections(assignments={}, rejected_sources=frozenset({"甲.png"})),
            players,
        )

        self.assertEqual(handled_count, 1)
        self.assertEqual(resolved[0].status, "rejected")
        self.assertIn("不导入", resolved[0].reason)

    def test_manual_selection_rejects_same_source_for_multiple_players(self):
        self.touch_photo("portrait.png")
        players = [Player("player-a", "甲"), Player("player-b", "乙")]
        matches = match_photos(
            self.folder,
            list_photo_files(self.folder, set()),
            players,
        )

        with self.assertRaisesRegex(ValueError, "同一图片不能分配给多位选手"):
            apply_manual_selections(
                self.folder,
                matches,
                ManualSelections(
                    assignments={
                        "player-a": "portrait.png",
                        "player-b": "portrait.png",
                    }
                ),
                players,
            )

    def test_loads_versioned_and_legacy_manual_selection_files(self):
        versioned_path = self.folder / "versioned.json"
        versioned_path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "assignments": {"player-a": "子目录/a.png"},
                    "rejected_sources": ["poster.png"],
                }
            ),
            encoding="utf-8",
        )
        legacy_path = self.folder / "legacy.json"
        legacy_path.write_text(
            json.dumps({"player-b": "b.jpg"}),
            encoding="utf-8",
        )

        versioned = load_manual_selections(str(versioned_path))
        legacy = load_manual_selections(str(legacy_path))

        self.assertEqual(versioned.assignments, {"player-a": "子目录/a.png"})
        self.assertEqual(versioned.rejected_sources, frozenset({"poster.png"}))
        self.assertEqual(legacy.assignments, {"player-b": "b.jpg"})
        self.assertEqual(legacy.rejected_sources, frozenset())

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

    def test_oversized_matched_photo_is_compressed_without_changing_source(self):
        path = self.folder / "Moony.png"
        original = b"\x89PNG\r\n\x1a\n" + b"x" * MAX_UPLOAD_BYTES
        path.write_bytes(original)
        players = [Player("player-moony-2", "Moony")]

        matches = match_photos(
            self.folder,
            list_photo_files(self.folder, set()),
            players,
        )
        self.assertEqual(matches[0].status, "included")

        compression_results = {}
        output = self.folder / "output.zip"

        def fake_compressor(source_path, target_bytes):
            self.assertEqual(source_path, path.resolve())
            self.assertLessEqual(target_bytes, MAX_UPLOAD_BYTES)
            payload = b"\xff\xd8\xffcompressed"
            return payload, ".jpg", CompressionResult(
                original_bytes=len(original),
                output_bytes=len(payload),
                output_extension=".jpg",
            )

        self.assertEqual(
            write_zip(
                output,
                matches,
                compression_results,
                compressor=fake_compressor,
            ),
            1,
        )
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(compression_results[path.resolve()].output_extension, ".jpg")
        with ZipFile(output) as archive:
            self.assertEqual(archive.namelist(), ["player-moony-2.jpg"])
            self.assertEqual(archive.read("player-moony-2.jpg"), b"\xff\xd8\xffcompressed")

    def test_archive_budget_compresses_individually_valid_photos(self):
        first = self.folder / "甲.png"
        second = self.folder / "乙.png"
        first.write_bytes(b"\x89PNG\r\n\x1a\n" + b"a" * 150_000)
        second.write_bytes(b"\x89PNG\r\n\x1a\n" + b"b" * 150_000)
        players = [Player("player-a", "甲"), Player("player-b", "乙")]
        matches = match_photos(
            self.folder,
            list_photo_files(self.folder, set()),
            players,
        )
        requested_targets = []

        def fake_compressor(source_path, target_bytes):
            requested_targets.append((source_path, target_bytes))
            payload = b"\xff\xd8\xff" + b"c" * 1_000
            return payload, ".jpg", CompressionResult(
                original_bytes=source_path.stat().st_size,
                output_bytes=len(payload),
                output_extension=".jpg",
            )

        output = self.folder / "output.zip"
        compression_results = {}
        write_zip(
            output,
            matches,
            compression_results,
            compressor=fake_compressor,
            archive_payload_budget_bytes=200 * 1024,
            archive_target_bytes=250 * 1024,
        )

        self.assertEqual(len(requested_targets), 2)
        self.assertTrue(all(target < 150_000 for _path, target in requested_targets))
        self.assertLess(output.stat().st_size, 250 * 1024)
        with ZipFile(output) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"player-a.jpg", "player-b.jpg"},
            )

    @unittest.skipIf(PILImage is None, "Pillow is only bundled for the macOS matcher build")
    def test_real_oversized_png_is_reencoded_below_server_limit(self):
        path = self.folder / "Moony.png"
        image = PILImage.effect_noise((3000, 3000), 100).convert("RGB")
        image.save(path, format="PNG")
        self.assertGreater(path.stat().st_size, MAX_UPLOAD_BYTES)
        players = [Player("player-moony-2", "Moony")]
        matches = match_photos(
            self.folder,
            list_photo_files(self.folder, set()),
            players,
        )

        output = self.folder / "output.zip"
        compression_results = {}
        write_zip(output, matches, compression_results)

        with ZipFile(output) as archive:
            payload = archive.read("player-moony-2.jpg")
        self.assertLessEqual(len(payload), MAX_UPLOAD_BYTES)
        self.assertEqual(PILImage.open(BytesIO(payload)).format, "JPEG")
        self.assertIn(path.resolve(), compression_results)

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
