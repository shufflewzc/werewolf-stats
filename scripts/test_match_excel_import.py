import unittest
from copy import deepcopy
from unittest.mock import patch

from competition_meta import default_scoring_rule
from generate_match_result_excel_template import (
    build_dynamic_match_template_bytes,
    build_multi_sheet_workbook_bytes,
)
from web.features import matches as matches_feature
from web_app import RequestContext, UploadedFile
from validate_data import validate_matches


RECORD_COLUMNS = [
    ("match_id", "比赛编号"),
    ("competition_name", "赛事名称"),
    ("season_name", "赛季"),
    ("played_on", "日期"),
    ("stage", "赛段"),
    ("seat", "座位号"),
    ("team_name", "战队名"),
    ("player_name", "选手"),
    ("role", "身份"),
    ("camp", "阵营"),
    ("points_earned", "单局积分"),
    ("format", "板型"),
    ("winning_camp", "胜利阵营"),
]


def build_match(
    match_id: str,
    competition_name: str,
    season_name: str,
    played_on: str,
    scoring_rule: dict,
) -> dict:
    match = matches_feature.build_placeholder_match(
        competition_name,
        season_name,
        "regular_season",
        1,
        1,
        played_on,
        "",
        "1号房",
    )
    match["match_id"] = match_id
    match["scoring_rule"] = deepcopy(scoring_rule)
    match["score_model"] = scoring_rule["score_model"]
    return match


def build_upload(rows: list[dict], *, filename: str = "matches.xlsx") -> UploadedFile:
    payload = build_multi_sheet_workbook_bytes(
        [("records", RECORD_COLUMNS, rows)]
    )
    return UploadedFile(
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=payload,
    )


def build_row(match_id: str, seat: int = 1, **overrides: object) -> dict:
    row = {
        "match_id": match_id,
        "competition_name": "文档伪造赛事",
        "season_name": "文档伪造赛季",
        "played_on": "2030-01-01",
        "stage": "final",
        "seat": seat,
        "team_name": "测试战队",
        "player_name": f"测试选手{seat}",
        "role": "村民",
        "camp": "villagers",
        "points_earned": 5,
        "format": "经典十二人局",
        "winning_camp": "villagers",
    }
    row.update(overrides)
    return row


class MatchExcelImportTests(unittest.TestCase):
    def setUp(self):
        self.standard_rule = default_scoring_rule("standard")
        self.ctx = RequestContext(
            method="POST",
            path="/matches/new",
            query={},
            form={},
            files={},
            current_user={"username": "admin", "role": "admin"},
            now_label="2026-08-17 12:00:00 中国时间",
        )

    def test_batch_create_placeholders_match_repository_schema(self):
        matches = matches_feature.batch_create_matches(
            "测试赛事",
            "测试赛季",
            "regular_season",
            "2026-08-27",
            "2026-08-27",
            1,
            3,
            "1号房",
        )

        self.assertEqual(3, len(matches))
        normalized_matches, _ = matches_feature.canonicalize_match_ids(matches)
        self.assertEqual([], validate_matches(normalized_matches, set(), set()))

    def import_rows(
        self,
        data: dict,
        rows: list[dict],
        *,
        permission_side_effect=None,
    ):
        return self.import_upload(
            data,
            build_upload(rows),
            permission_side_effect=permission_side_effect,
        )

    def import_upload(
        self,
        data: dict,
        upload: UploadedFile,
        *,
        permission_side_effect=None,
    ):
        permission_value = True if permission_side_effect is None else None
        with (
            patch.object(
                matches_feature,
                "can_manage_competition_action",
                return_value=permission_value,
                side_effect=(
                    None
                    if permission_side_effect is None
                    else lambda user, scoped_data, competition, _permission: permission_side_effect(
                        user, scoped_data, competition
                    )
                ),
            ),
            patch.object(matches_feature, "validate_match_competition_selection", return_value=""),
            patch.object(matches_feature, "validate_match_season_selection", return_value=""),
            patch.object(matches_feature, "resolve_match_entities", return_value=[]),
        ):
            metadata: dict[str, object] = {}
            next_matches, message = matches_feature.import_matches_from_excel(
                self.ctx,
                data,
                upload,
                result_metadata=metadata,
            )
        return next_matches, message, metadata

    def test_import_panel_uses_match_id_instead_of_season_picker(self):
        ctx = RequestContext(
            method="GET",
            path="/matches/new",
            query={},
            form={},
            files={},
            current_user={"username": "admin", "role": "admin"},
            now_label="2026-08-17 12:00:00 中国时间",
        )
        with (
            patch.object(matches_feature, "load_validated_data", return_value={}),
            patch.object(matches_feature, "load_series_catalog", return_value=[]),
        ):
            html = matches_feature.build_excel_import_panel(ctx)

        self.assertIn('name="match_id"', html)
        self.assertNotIn("模板所属赛季", html)
        self.assertNotIn('name="season"', html)

    def test_dynamic_template_prefills_requested_match_id(self):
        payload = build_dynamic_match_template_bytes(
            "赛事A",
            "赛季A",
            self.standard_rule,
            "aa-s1-260817-01",
        )
        upload = UploadedFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", payload)

        rows = matches_feature.read_excel_sheet_rows(upload, "records")
        metadata = matches_feature.read_scoring_template_metadata(upload)

        self.assertTrue(rows)
        self.assertEqual({row["match_id"] for row in rows}, {"aa-s1-260817-01"})
        self.assertEqual(metadata["competition_name"], "赛事A")
        self.assertEqual(metadata["season_name"], "赛季A")

    def test_template_download_resolves_scope_and_rule_from_match_id(self):
        existing = build_match(
            "aa-s1-260817-01",
            "赛事A",
            "赛季A",
            "2026-08-17",
            self.standard_rule,
        )
        ctx = RequestContext(
            method="GET",
            path="/matches/new",
            query={
                "action": ["download_scoring_template"],
                "match_id": [existing["match_id"]],
            },
            form={},
            files={},
            current_user={"username": "admin", "role": "admin"},
            now_label="2026-08-17 12:00:00 中国时间",
        )
        response: dict[str, object] = {}

        def start_response(status, headers):
            response["status"] = status
            response["headers"] = dict(headers)

        with (
            patch.object(matches_feature, "load_validated_data", return_value={"matches": [existing]}),
            patch.object(matches_feature, "can_manage_matches", return_value=True),
            patch.object(matches_feature, "validate_match_competition_selection", return_value=""),
            patch.object(matches_feature, "validate_match_season_selection", return_value=""),
        ):
            payload_parts = matches_feature.handle_match_create(ctx, start_response)

        payload = b"".join(payload_parts)
        upload = UploadedFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", payload)
        rows = matches_feature.read_excel_sheet_rows(upload, "records")
        self.assertEqual(response["status"], "200 OK")
        self.assertIn(existing["match_id"], response["headers"]["Content-Disposition"])
        self.assertEqual({row["match_id"] for row in rows}, {existing["match_id"]})

    def test_legacy_template_download_query_remains_supported(self):
        ctx = RequestContext(
            method="GET",
            path="/matches/new",
            query={
                "action": ["download_scoring_template"],
                "competition_name": ["赛事A"],
                "season": ["赛季A"],
            },
            form={},
            files={},
            current_user={"username": "admin", "role": "admin"},
            now_label="2026-08-17 12:00:00 中国时间",
        )
        response: dict[str, object] = {}

        def start_response(status, headers):
            response["status"] = status
            response["headers"] = dict(headers)

        with (
            patch.object(matches_feature, "load_validated_data", return_value={"matches": []}),
            patch.object(matches_feature, "can_manage_matches", return_value=True),
            patch.object(matches_feature, "validate_match_competition_selection", return_value=""),
            patch.object(matches_feature, "validate_match_season_selection", return_value=""),
            patch.object(matches_feature, "resolve_scoring_rule_for_scope", return_value=self.standard_rule),
        ):
            payload_parts = matches_feature.handle_match_create(ctx, start_response)

        self.assertEqual(response["status"], "200 OK")
        self.assertTrue(b"".join(payload_parts).startswith(b"PK"))

    def test_old_template_with_match_id_ignores_forged_scope_fields(self):
        existing = build_match(
            "aa-s1-260817-01",
            "真实赛事",
            "真实赛季S1",
            "2026-08-17",
            self.standard_rule,
        )
        data = {"matches": [existing], "teams": [], "players": []}

        next_matches, message, metadata = self.import_rows(
            data,
            [build_row(existing["match_id"])],
        )

        self.assertIsNotNone(next_matches)
        updated = next_matches[0]
        self.assertEqual(updated["competition_name"], "真实赛事")
        self.assertEqual(updated["season"], "真实赛季S1")
        self.assertEqual(updated["played_on"], "2026-08-17")
        self.assertEqual(updated["stage"], "regular_season")
        self.assertIn("更新 1 场", message)
        self.assertEqual(metadata["matched_match_ids"], [existing["match_id"]])

    def test_old_two_sheet_template_updates_existing_match_even_in_create_mode(self):
        existing = build_match(
            "aa-s1-260817-01",
            "真实赛事",
            "真实赛季S1",
            "2026-08-17",
            self.standard_rule,
        )
        payload = build_multi_sheet_workbook_bytes(
            [
                (
                    "matches",
                    [
                        ("match_key", "match_key"),
                        ("import_mode", "import_mode"),
                        ("match_id", "比赛编号"),
                        ("format", "板型"),
                        ("winning_camp", "胜利阵营"),
                    ],
                    [
                        {
                            "match_key": "legacy-row-1",
                            "import_mode": "create",
                            "match_id": existing["match_id"],
                            "format": "经典十二人局",
                            "winning_camp": "villagers",
                        }
                    ],
                ),
                (
                    "players",
                    [
                        ("match_key", "match_key"),
                        ("seat", "座位号"),
                        ("team_name", "战队名"),
                        ("player_name", "选手"),
                        ("role", "身份"),
                        ("camp", "阵营"),
                        ("points_earned", "单局积分"),
                    ],
                    [
                        {
                            "match_key": "legacy-row-1",
                            "seat": 1,
                            "team_name": "测试战队",
                            "player_name": "测试选手",
                            "role": "村民",
                            "camp": "villagers",
                            "points_earned": 5,
                        }
                    ],
                ),
            ]
        )
        upload = UploadedFile(
            "legacy.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            payload,
        )
        data = {"matches": [existing], "teams": [], "players": []}

        next_matches, message, _ = self.import_upload(data, upload)

        self.assertIsNotNone(next_matches)
        self.assertEqual(len(next_matches), 1)
        self.assertEqual(next_matches[0]["match_id"], existing["match_id"])
        self.assertIn("更新 1 场", message)

    def test_import_rejects_missing_or_unknown_match_id(self):
        existing = build_match(
            "aa-s1-260817-01",
            "赛事A",
            "赛季A",
            "2026-08-17",
            self.standard_rule,
        )
        data = {"matches": [existing], "teams": [], "players": []}

        missing_matches, missing_message, _ = self.import_rows(data, [build_row("")])
        unknown_matches, unknown_message, _ = self.import_rows(data, [build_row("missing-id")])

        self.assertIsNone(missing_matches)
        self.assertIn("必须填写唯一比赛编号", missing_message)
        self.assertIsNone(unknown_matches)
        self.assertIn("没有找到比赛编号：missing-id", unknown_message)

    def test_import_rejects_conflicting_match_fields_for_same_id(self):
        existing = build_match(
            "aa-s1-260817-01",
            "赛事A",
            "赛季A",
            "2026-08-17",
            self.standard_rule,
        )
        data = {"matches": [existing], "teams": [], "players": []}

        next_matches, message, _ = self.import_rows(
            data,
            [
                build_row(existing["match_id"], seat=1, winning_camp="villagers"),
                build_row(existing["match_id"], seat=2, winning_camp="werewolves"),
            ],
        )

        self.assertIsNone(next_matches)
        self.assertIn(f"比赛 {existing['match_id']} 的胜利阵营在多行中不一致", message)

    def test_mixed_seasons_with_same_rule_are_imported_together(self):
        first = build_match("aa-s1-260817-01", "赛事A", "赛季S1", "2026-08-17", self.standard_rule)
        second = build_match("aa-s2-260818-01", "赛事A", "赛季S2", "2026-08-18", self.standard_rule)
        data = {"matches": [first, second], "teams": [], "players": []}

        next_matches, message, metadata = self.import_rows(
            data,
            [build_row(first["match_id"]), build_row(second["match_id"])],
        )

        self.assertIsNotNone(next_matches)
        self.assertIn("更新 2 场", message)
        self.assertEqual(len(metadata["matched_scopes"]), 2)

    def test_mixed_incompatible_rules_are_rejected_as_one_batch(self):
        first = build_match("aa-s1-260817-01", "赛事A", "赛季S1", "2026-08-17", self.standard_rule)
        second = build_match(
            "aa-s2-260818-01",
            "赛事A",
            "赛季S2",
            "2026-08-18",
            default_scoring_rule("jingcheng_daily"),
        )
        data = {"matches": [first, second], "teams": [], "players": []}

        next_matches, message, _ = self.import_rows(
            data,
            [build_row(first["match_id"]), build_row(second["match_id"])],
        )

        self.assertIsNone(next_matches)
        self.assertIn("计分规则不兼容", message)
        self.assertIn(first["match_id"], message)
        self.assertIn(second["match_id"], message)

    def test_mixed_competitions_reject_when_any_scope_is_unauthorized(self):
        first = build_match("aa-s1-260817-01", "赛事A", "赛季S1", "2026-08-17", self.standard_rule)
        second = build_match("bb-s1-260817-01", "赛事B", "赛季S1", "2026-08-17", self.standard_rule)
        data = {"matches": [first, second], "teams": [], "players": []}

        next_matches, message, _ = self.import_rows(
            data,
            [build_row(first["match_id"]), build_row(second["match_id"])],
            permission_side_effect=lambda _user, _data, competition: competition == "赛事A",
        )

        self.assertIsNone(next_matches)
        self.assertIn("你没有权限导入 赛事B", message)


if __name__ == "__main__":
    unittest.main()
