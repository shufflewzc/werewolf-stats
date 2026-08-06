import unittest
from unittest.mock import patch

import competition_meta
import web_app
from competition_meta import (
    normalize_season_catalog_entry,
    normalize_stage_labels,
    resolve_stage_label_for_scope,
    stage_label_for_season_entry,
    stage_options_for_season_entry,
)
from web.features.series_manage import (
    build_stage_window_form_values,
    collect_stage_labels_from_form,
    render_season_policy_editor,
    validate_stage_labels,
)


class StageLabelTests(unittest.TestCase):
    def test_normalization_keeps_known_non_empty_labels(self):
        self.assertEqual(
            normalize_stage_labels(
                {
                    "placement": "  海选赛  ",
                    "regular_season": "",
                    "unknown": "不应保存",
                }
            ),
            {"placement": "海选赛"},
        )

    def test_season_entry_uses_custom_labels_with_default_fallback(self):
        entry = normalize_season_catalog_entry(
            {
                "series_slug": "sample",
                "series_name": "示例赛事",
                "series_code": "SAMPLE",
                "competition_name": "示例赛事广州站",
                "season_name": "S1",
                "stage_labels": {
                    "placement": "海选赛",
                    "finals": "巅峰赛",
                },
            }
        )
        self.assertIsNotNone(entry)
        self.assertEqual(stage_label_for_season_entry(entry, "placement"), "海选赛")
        self.assertEqual(stage_label_for_season_entry(entry, "regular_season"), "常规赛")
        self.assertEqual(stage_options_for_season_entry(entry)["finals"], "巅峰赛")

    def test_scope_resolution_isolated_by_competition_and_season(self):
        series_catalog = [
            {
                "series_slug": "sample",
                "competition_name": "示例赛事广州站",
            },
            {
                "series_slug": "sample",
                "competition_name": "示例赛事北京站",
            },
        ]
        season_catalog = [
            {
                "series_slug": "sample",
                "competition_name": "示例赛事广州站",
                "season_name": "S1",
                "stage_labels": {"regular_season": "积分循环赛"},
            },
            {
                "series_slug": "sample",
                "competition_name": "示例赛事北京站",
                "season_name": "S1",
                "stage_labels": {"regular_season": "城市联赛"},
            },
        ]
        with patch.object(
            competition_meta,
            "load_series_catalog",
            return_value=series_catalog,
        ), patch.object(
            competition_meta,
            "load_season_catalog",
            return_value=season_catalog,
        ):
            self.assertEqual(
                resolve_stage_label_for_scope(
                    {}, "示例赛事广州站", "S1", "regular_season"
                ),
                "积分循环赛",
            )
            self.assertEqual(
                resolve_stage_label_for_scope(
                    {}, "示例赛事北京站", "S1", "regular_season"
                ),
                "城市联赛",
            )
            self.assertEqual(
                resolve_stage_label_for_scope(
                    {}, "示例赛事广州站", "S2", "regular_season"
                ),
                "常规赛",
            )

    def test_validation_rejects_duplicate_and_overlong_labels(self):
        self.assertIn("不能重复", validate_stage_labels({"placement": "常规赛"}))
        self.assertIn("不能超过", validate_stage_labels({"placement": "超" * 21}))
        self.assertEqual(
            validate_stage_labels(
                {"placement": "海选赛", "regular_season": "积分循环赛"}
            ),
            "",
        )

    def test_admin_form_round_trips_custom_labels(self):
        values = build_stage_window_form_values(
            {"stage_labels": {"regular_season": "积分循环赛"}}
        )
        self.assertEqual(values["stage_regular_season_label"], "积分循环赛")
        self.assertEqual(
            collect_stage_labels_from_form(
                {
                    "stage_regular_season_label": [" 积分循环赛 "],
                    "stage_finals_label": ["巅峰赛"],
                }
            ),
            {"regular_season": "积分循环赛", "finals": "巅峰赛"},
        )
        editor = render_season_policy_editor(
            None,
            "season_policy",
            display_stage_options={
                **stage_options_for_season_entry(None),
                "regular_season": "积分循环赛",
            },
        )
        self.assertIn("积分循环赛", editor)

    def test_player_history_uses_scoped_custom_label(self):
        series_catalog = [
            {
                "series_slug": "sample",
                "competition_name": "示例赛事广州站",
            }
        ]
        season_catalog = [
            {
                "series_slug": "sample",
                "competition_name": "示例赛事广州站",
                "season_name": "S1",
                "stage_labels": {"regular_season": "积分循环赛"},
            }
        ]
        base_details = {
            "player-1": {
                "history": [
                    {
                        "competition_name": "示例赛事广州站",
                        "season": "S1",
                        "stage": "regular_season",
                        "stage_label": "常规赛",
                    }
                ]
            }
        }
        with patch.object(
            web_app,
            "build_base_player_details",
            return_value=base_details,
        ), patch.object(
            competition_meta,
            "load_series_catalog",
            return_value=series_catalog,
        ), patch.object(
            competition_meta,
            "load_season_catalog",
            return_value=season_catalog,
        ):
            details = web_app.build_player_details({}, [])
        self.assertEqual(
            details["player-1"]["history"][0]["stage_label"],
            "积分循环赛",
        )


if __name__ == "__main__":
    unittest.main()
