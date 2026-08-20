from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_app
from web.features import console


class ConsoleFeatureTests(unittest.TestCase):
    def setUp(self):
        self.catalog = [
            {
                "competition_name": "深圳联赛",
                "region_name": "深圳市",
                "series_slug": "sz-league",
                "series_name": "深圳联赛",
            },
            {
                "competition_name": "北京联赛",
                "region_name": "北京市",
                "series_slug": "bj-league",
                "series_name": "北京联赛",
            },
        ]
        self.data = {
            "matches": [
                {
                    "match_id": "sz-s4-260813-01",
                    "competition_name": "深圳联赛",
                    "season": "S4",
                    "stage": "regular_season",
                    "round": 8,
                    "game_no": 1,
                    "played_on": "2026-08-13",
                    "group_label": "A组",
                    "table_label": "1号房",
                    "format": "经典十二人局",
                    "exclude_from_team_scores": False,
                    "players": [
                        {"player_id": "p-tian", "team_id": "t-bean"},
                        {"player_id": "p-timmy", "team_id": "t-red"},
                    ],
                },
                {
                    "match_id": "sz-s4-260814-02",
                    "competition_name": "深圳联赛",
                    "season": "S4",
                    "stage": "regular_season",
                    "round": 8,
                    "game_no": 2,
                    "played_on": "2026-08-14",
                    "group_label": "B组",
                    "table_label": "2号房",
                    "format": "待补录",
                    "exclude_from_team_scores": True,
                    "players": [],
                },
                {
                    "match_id": "bj-s2-260812-01",
                    "competition_name": "北京联赛",
                    "season": "S2",
                    "stage": "playoffs",
                    "round": 2,
                    "game_no": 1,
                    "played_on": "2026-08-12",
                    "group_label": "决赛组",
                    "table_label": "主舞台",
                    "format": "经典十二人局",
                    "exclude_from_team_scores": False,
                    "players": [{"player_id": "p-secret", "team_id": "t-secret"}],
                },
            ],
            "players": [
                {"player_id": "p-tian", "display_name": "甜晓C"},
                {"player_id": "p-timmy", "display_name": "Timmy"},
                {"player_id": "p-secret", "display_name": "未授权选手"},
            ],
            "teams": [
                {"team_id": "t-bean", "name": "我嘞个豆行动"},
                {"team_id": "t-red", "name": "红山派"},
                {"team_id": "t-secret", "name": "未授权战队"},
            ],
        }
        self.user = {
            "username": "shenzhen-result-editor",
            "role": "event_manager",
            "scope_grants": [
                {
                    "scope_key": "深圳市::sz-league",
                    "permissions": ["match_result_manage", "scope_audit_view"],
                    "is_scope_admin": False,
                }
            ],
        }

        def has_permission(user, scope_key, permission_key):
            return any(
                grant.get("scope_key") == scope_key
                and (
                    grant.get("is_scope_admin")
                    or permission_key in grant.get("permissions", [])
                )
                for grant in (user or {}).get("scope_grants", [])
            )

        self.patches = [
            patch.object(console, "load_validated_data", return_value=self.data),
            patch.object(console, "load_series_catalog", return_value=self.catalog),
            patch.object(
                console,
                "list_seasons",
                side_effect=lambda _data, competition, **_kwargs: (
                    ["S4"] if competition == "深圳联赛" else ["S2"]
                ),
            ),
            patch.object(
                console,
                "resolve_stage_options_for_scope",
                return_value={"regular_season": "常规赛", "playoffs": "季后赛"},
            ),
            patch.object(console, "load_import_batches", return_value=[]),
            patch.object(
                console,
                "layout",
                side_effect=lambda _title, body, _ctx, alert="": (
                    (f'<div class="alert">{alert}</div>' if alert else "") + body
                ),
            ),
            patch.object(
                console.legacy,
                "user_has_scope_permission",
                side_effect=has_permission,
                create=True,
            ),
            patch.object(
                console.legacy,
                "user_has_any_scope_permission",
                side_effect=lambda user, scope, keys: any(
                    has_permission(user, scope, key) for key in keys
                ),
                create=True,
            ),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def context(self, path="/console/matches", query=None, user=None, method="GET"):
        return web_app.RequestContext(
            method=method,
            path=path,
            query=query or {},
            form={},
            files={},
            current_user=self.user if user is None else user,
            now_label="2026-08-20 10:00:00 中国时间",
        )

    def test_match_list_is_permission_filtered_before_rendering(self):
        ctx = self.context(
            query={"competition": [""], "season": [""]}
        )
        html = console.get_console_matches_page(ctx)
        self.assertIn("sz-s4-260813-01", html)
        self.assertIn("深圳联赛", html)
        self.assertNotIn("bj-s2-260812-01", html)
        self.assertNotIn("未授权战队", html)
        self.assertNotIn("未授权选手", html)

    def test_search_finds_team_player_date_room_and_format(self):
        accessible = self.data["matches"][:2]
        cases = {
            "我嘞个豆行动": "sz-s4-260813-01",
            "timmy": "sz-s4-260813-01",
            "2026-08-14": "sz-s4-260814-02",
            "2号房": "sz-s4-260814-02",
            "经典十二人局": "sz-s4-260813-01",
        }
        for keyword, expected_id in cases.items():
            with self.subTest(keyword=keyword):
                result = console.filter_console_matches(
                    self.data, accessible, keyword=keyword
                )
                self.assertEqual([item["match_id"] for item in result], [expected_id])

    def test_status_date_and_team_score_filters_compose(self):
        result = console.filter_console_matches(
            self.data,
            self.data["matches"][:2],
            competition_name="深圳联赛",
            season_name="S4",
            date_from="2026-08-14",
            date_to="2026-08-14",
            record_status="pending",
            team_score="excluded",
        )
        self.assertEqual(
            [item["match_id"] for item in result], ["sz-s4-260814-02"]
        )

    def test_exact_match_id_offers_direct_open_and_edit(self):
        ctx = self.context(
            query={
                "competition": ["深圳联赛"],
                "season": ["S4"],
                "q": ["SZ-S4-260813-01"],
            }
        )
        html = console.get_console_matches_page(ctx)
        self.assertIn("已精确匹配比赛编号", html)
        self.assertIn('/matches/sz-s4-260813-01/edit', html)

    def test_overview_hides_tasks_without_scope_permission(self):
        ctx = self.context(path="/console")
        html = console.get_console_page(ctx)
        self.assertIn("搜索与编辑比赛", html)
        self.assertNotIn("新增单场比赛", html)
        self.assertNotIn("上传比赛数据", html)
        self.assertIn("sz-s4-260814-02", html)

    def test_recent_imports_require_matching_action_permission_for_every_scope(self):
        upload_user = {
            "username": "shenzhen-importer",
            "role": "event_manager",
            "scope_grants": [
                {
                    "scope_key": "深圳市::sz-league",
                    "permissions": ["match_import_manage"],
                    "is_scope_admin": False,
                }
            ],
        }
        batches = [
            {
                "batch_id": "allowed",
                "action": "matches.import_excel",
                "created_by": "coworker",
                "metadata": {"permission_scope_keys": ["深圳市::sz-league"]},
            },
            {
                "batch_id": "wrong-action",
                "action": "dimension.import_excel",
                "created_by": "coworker",
                "metadata": {"permission_scope_keys": ["深圳市::sz-league"]},
            },
            {
                "batch_id": "cross-scope",
                "action": "matches.import_excel",
                "created_by": "coworker",
                "metadata": {
                    "permission_scope_keys": [
                        "深圳市::sz-league",
                        "北京市::bj-league",
                    ]
                },
            },
            {
                "batch_id": "owned-legacy",
                "action": "matches.import_excel",
                "created_by": "shenzhen-importer",
                "metadata": {},
            },
        ]
        ctx = self.context(path="/console", user=upload_user)
        with patch.object(console, "load_import_batches", return_value=batches):
            visible = console._visible_import_batches(
                ctx,
                self.data,
                {"深圳联赛"},
            )
        self.assertEqual(
            [str(item.get("batch_id") or "") for item in visible],
            ["allowed", "owned-legacy"],
        )

    def test_creator_cannot_view_scoped_batch_after_that_scope_is_revoked(self):
        user_with_other_scope = {
            "username": "multi-scope-importer",
            "role": "event_manager",
            "scope_grants": [
                {
                    "scope_key": "北京市::bj-league",
                    "permissions": ["match_import_manage"],
                    "is_scope_admin": False,
                }
            ],
        }
        batches = [
            {
                "batch_id": "revoked-shenzhen-batch",
                "action": "matches.import_excel",
                "created_by": "multi-scope-importer",
                "metadata": {"permission_scope_keys": ["深圳市::sz-league"]},
            },
            {
                "batch_id": "current-beijing-batch",
                "action": "matches.import_excel",
                "created_by": "multi-scope-importer",
                "metadata": {"permission_scope_keys": ["北京市::bj-league"]},
            },
        ]
        ctx = self.context(path="/console", user=user_with_other_scope)

        with patch.object(console, "load_import_batches", return_value=batches):
            visible = console._visible_import_batches(
                ctx,
                self.data,
                {"北京联赛"},
            )

        self.assertEqual(
            [str(item.get("batch_id") or "") for item in visible],
            ["current-beijing-batch"],
        )

    def test_filter_parameters_survive_pagination(self):
        expanded = []
        for index in range(12):
            item = dict(self.data["matches"][0])
            item["match_id"] = f"sz-s4-260813-{index + 1:02d}"
            expanded.append(item)
        self.data["matches"] = expanded + [self.data["matches"][2]]
        ctx = self.context(
            query={
                "competition": ["深圳联赛"],
                "season": ["S4"],
                "q": ["红山派"],
                "per_page": ["10"],
            }
        )
        html = console.get_console_matches_page(ctx)
        self.assertIn("page=2", html)
        self.assertIn("q=%E7%BA%A2%E5%B1%B1%E6%B4%BE", html)
        self.assertIn("per_page=10", html)

    def test_handlers_redirect_anonymous_and_reject_post(self):
        statuses = []
        anonymous = self.context(path="/console", user={})
        response = console.handle_console(
            anonymous,
            lambda status, headers: statuses.append((status, dict(headers))),
        )
        self.assertEqual(statuses[0][0], "302 Found")
        self.assertIn("/login?next=", statuses[0][1]["Location"])
        self.assertEqual(response, [b""])

        statuses.clear()
        post_ctx = self.context(path="/console/matches", method="POST")
        console.handle_console_matches(
            post_ctx,
            lambda status, headers: statuses.append((status, dict(headers))),
        )
        self.assertEqual(statuses[0][0], "405 Method Not Allowed")
        self.assertEqual(statuses[0][1]["Allow"], "GET")


if __name__ == "__main__":
    unittest.main()
