import unittest
from unittest.mock import patch

import competition_meta
import season_grouping
import web_app
from competition_meta import (
    normalize_season_catalog_entry,
    normalize_stage_labels,
    resolve_stage_label_for_scope,
    resolve_stage_title_for_scope,
    stage_label_for_season_entry,
    stage_options_for_season_entry,
)
from web.features import matches as matches_feature
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

    def test_generated_stage_titles_follow_custom_label(self):
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
                resolve_stage_title_for_scope(
                    {},
                    "示例赛事广州站",
                    "S1",
                    "regular_season",
                    "S组常规赛榜",
                    "S组",
                ),
                "S组积分循环赛榜",
            )
            self.assertEqual(
                resolve_stage_title_for_scope(
                    {},
                    "示例赛事广州站",
                    "S1",
                    "regular_season",
                    "荣耀战队榜",
                    "S组",
                ),
                "荣耀战队榜",
            )

    def test_grouped_leaderboard_api_section_uses_custom_title(self):
        policy = {
            "stages": {
                "regular_season": {
                    "standings": {
                        "mode": "tiered",
                        "sections": [
                            {
                                "key": "S",
                                "label": "S组",
                                "title": "S组常规赛榜",
                                "groups": ["S1"],
                            }
                        ],
                    }
                }
            }
        }
        with patch.object(
            season_grouping,
            "resolve_policy",
            return_value=policy,
        ), patch.object(
            season_grouping,
            "build_regular_season_team_leaderboards",
            return_value={"S": []},
        ), patch.object(
            competition_meta,
            "resolve_stage_label_for_scope",
            return_value="积分循环赛",
        ):
            sections = season_grouping.build_team_leaderboard_sections(
                {},
                "示例赛事广州站",
                "S1",
                "regular_season",
            )
        self.assertEqual(sections[0]["title"], "S组积分循环赛榜")

    def test_dashboard_progression_copy_uses_custom_stage_labels(self):
        custom_labels = {
            **stage_options_for_season_entry(None),
            "regular_season": "积分循环赛",
            "playoffs": "晋级赛",
            "finals": "巅峰赛",
        }
        with patch.object(
            web_app,
            "resolve_stage_options_for_scope",
            return_value=custom_labels,
        ), patch.object(
            web_app,
            "progression_is_display_only",
            return_value=False,
        ):
            context = web_app.build_dashboard_promotion_context(
                {"teams": [], "players": []},
                [],
                "示例赛事广州站",
                "S1",
                "广州",
                "sample",
            )
        self.assertEqual(context["stage_labels"]["finals"], "巅峰赛")
        self.assertTrue(any("积分循环赛" in item for item in context["rules"]))
        self.assertTrue(any("晋级赛" in item for item in context["rules"]))

    def test_match_stage_validation_uses_stable_stage_keys(self):
        with patch.object(
            web_app,
            "resolve_stage_options_for_scope",
            return_value={"regular_season": "积分循环赛", "finals": "巅峰赛"},
        ):
            self.assertEqual(
                web_app.validate_match_stage_selection(
                    {}, "示例赛事广州站", "S1", "regular_season"
                ),
                "",
            )
            self.assertIn(
                "当前赛事赛季",
                web_app.validate_match_stage_selection(
                    {}, "示例赛事广州站", "S1", "unknown"
                ),
            )

    def test_match_season_picker_embeds_custom_stage_map(self):
        catalog = [
            {
                "competition_name": "示例赛事广州站",
                "region_name": "广州",
                "series_name": "示例赛事",
            }
        ]
        with patch.object(
            matches_feature,
            "load_validated_data",
            return_value={"matches": []},
        ), patch.object(
            matches_feature,
            "load_series_catalog",
            return_value=catalog,
        ), patch.object(
            matches_feature,
            "list_seasons",
            return_value=["S1"],
        ), patch.object(
            matches_feature,
            "resolve_stage_options_for_scope",
            return_value={"regular_season": "积分循环赛", "finals": "巅峰赛"},
        ):
            html = matches_feature.build_match_season_field(
                "示例赛事广州站",
                "S1",
                include_non_ongoing=True,
            )
        self.assertIn("data-stage-map", html)
        self.assertIn("积分循环赛", html)
        self.assertIn("data-match-stage-select", html)

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
