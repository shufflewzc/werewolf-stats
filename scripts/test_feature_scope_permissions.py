from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_app
from web.features import competitions, data_upload, profile, team_center, team_page
from web.features import matches as matches_feature
from web.features import team_center_v2


SCOPE_SHENZHEN = "深圳市::sz-league"
SCOPE_BEIJING = "北京市::bj-league"
COMPETITION_SCOPES = {
    "深圳联赛": SCOPE_SHENZHEN,
    "北京联赛": SCOPE_BEIJING,
}


def scoped_user(
    username: str,
    scope_key: str,
    permissions: list[str] | None = None,
    *,
    is_scope_admin: bool = False,
) -> dict[str, object]:
    return {
        "username": username,
        "role": "event_manager",
        "permissions": [],
        "scope_grants": [
            {
                "scope_key": scope_key,
                "permissions": permissions or [],
                "is_scope_admin": is_scope_admin,
            }
        ],
        "scope_grants_authoritative": True,
    }


def request_context(
    user: dict[str, object] | None,
    *,
    method: str = "GET",
    path: str = "/",
) -> web_app.RequestContext:
    return web_app.RequestContext(
        method=method,
        path=path,
        query={},
        form={},
        files={},
        current_user=user,
        now_label=web_app.china_now_label(),
    )


class ScopedEntryPointPermissionTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "matches": [
                {
                    "match_id": "sz-s4-260820-01",
                    "competition_name": "深圳联赛",
                    "season": "S4",
                },
                {
                    "match_id": "bj-s2-260820-01",
                    "competition_name": "北京联赛",
                    "season": "S2",
                },
            ],
            "teams": [],
            "players": [],
        }

    def scope_key_for_competition(self, _data, competition_name):
        return COMPETITION_SCOPES.get(competition_name, "")

    def test_schedule_and_result_controls_use_distinct_permissions(self):
        schedule_user = scoped_user(
            "schedule",
            SCOPE_SHENZHEN,
            ["match_schedule_manage"],
        )
        result_user = scoped_user(
            "result",
            SCOPE_SHENZHEN,
            ["match_result_manage"],
        )
        audit_user = scoped_user(
            "audit",
            SCOPE_SHENZHEN,
            ["scope_audit_view"],
        )

        with patch.object(
            web_app,
            "get_competition_scope_key",
            side_effect=self.scope_key_for_competition,
        ):
            self.assertTrue(
                competitions.can_create_match_in_competition(
                    schedule_user,
                    self.data,
                    "深圳联赛",
                )
            )
            self.assertFalse(
                competitions.can_create_match_in_competition(
                    result_user,
                    self.data,
                    "深圳联赛",
                )
            )
            self.assertFalse(
                competitions.can_create_match_in_competition(
                    schedule_user,
                    self.data,
                    "北京联赛",
                )
            )
            self.assertTrue(
                team_page.can_edit_match_from_team_page(
                    result_user,
                    self.data,
                    "深圳联赛",
                )
            )
            self.assertFalse(
                team_page.can_edit_match_from_team_page(
                    schedule_user,
                    self.data,
                    "深圳联赛",
                )
            )
            self.assertFalse(
                team_page.can_edit_match_from_team_page(
                    audit_user,
                    self.data,
                    "深圳联赛",
                )
            )
            self.assertFalse(
                team_page.can_edit_match_from_team_page(
                    result_user,
                    self.data,
                    "北京联赛",
                )
            )

    def test_legacy_match_manager_keeps_scoped_compatibility(self):
        legacy_user = {
            "username": "legacy",
            "role": "event_manager",
            "permissions": ["match_manage"],
            "manager_scope_keys": [SCOPE_SHENZHEN],
        }

        with patch.object(
            web_app,
            "get_competition_scope_key",
            side_effect=self.scope_key_for_competition,
        ):
            self.assertTrue(
                competitions.can_create_match_in_competition(
                    legacy_user,
                    self.data,
                    "深圳联赛",
                )
            )
            self.assertTrue(
                team_page.can_edit_match_from_team_page(
                    legacy_user,
                    self.data,
                    "深圳联赛",
                )
            )
            self.assertFalse(
                competitions.can_create_match_in_competition(
                    legacy_user,
                    self.data,
                    "北京联赛",
                )
            )
            self.assertEqual(
                [item["competition_name"] for item in data_upload.available_targets(legacy_user, self.data)],
                ["深圳联赛"],
            )

    def test_upload_targets_and_console_shortcut_respect_scoped_capabilities(self):
        import_user = scoped_user(
            "importer",
            SCOPE_SHENZHEN,
            ["match_import_manage"],
        )
        dimension_user = scoped_user(
            "dimension",
            SCOPE_BEIJING,
            ["dimension_data_manage"],
        )
        audit_user = scoped_user(
            "audit",
            SCOPE_SHENZHEN,
            ["scope_audit_view"],
        )

        with patch.object(
            web_app,
            "get_competition_scope_key",
            side_effect=self.scope_key_for_competition,
        ):
            self.assertEqual(
                [item["competition_name"] for item in data_upload.available_targets(import_user, self.data)],
                ["深圳联赛"],
            )
            self.assertEqual(
                [item["competition_name"] for item in data_upload.available_targets(dimension_user, self.data)],
                ["北京联赛"],
            )
            self.assertFalse(data_upload.can_manage_data_upload(audit_user))
            self.assertEqual(data_upload.token_panel(request_context(audit_user)), "")
            self.assertTrue(profile.can_access_event_console(audit_user))

    def test_desktop_upload_rejects_wrong_capability_before_parsing_or_write(self):
        cases = [
            (
                scoped_user("importer", SCOPE_SHENZHEN, ["match_import_manage"]),
                "dimension_file",
                "dimension.xlsx",
                "维度数据上传权限",
            ),
            (
                scoped_user("dimension", SCOPE_SHENZHEN, ["dimension_data_manage"]),
                "match_file",
                "match.xlsx",
                "比赛数据上传权限",
            ),
        ]
        for user, field_name, filename, expected_error in cases:
            with self.subTest(field_name=field_name):
                meta: dict[str, str] = {}

                def mutate_json_meta(key, fallback, mutator, **_kwargs):
                    raw = meta.get(key, "")
                    try:
                        current = json.loads(raw) if raw else fallback
                    except json.JSONDecodeError:
                        current = fallback
                    next_value, result = mutator(current)
                    if next_value is not None:
                        meta[key] = json.dumps(next_value, ensure_ascii=False)
                    return result

                with (
                    patch.object(data_upload.legacy, "load_meta_value", side_effect=lambda key: meta.get(key)),
                    patch.object(data_upload.legacy, "save_meta_value", side_effect=lambda key, value: meta.__setitem__(key, value)),
                    patch.object(data_upload, "mutate_json_meta_value", side_effect=mutate_json_meta),
                    patch.object(data_upload.legacy, "load_users", return_value=[user]),
                    patch.object(data_upload.legacy, "load_validated_data", return_value=self.data),
                    patch.object(web_app, "get_competition_scope_key", side_effect=self.scope_key_for_competition),
                    patch.object(matches_feature, "validate_excel_upload", return_value=""),
                    patch.object(matches_feature, "import_matches_from_excel") as parse_matches,
                    patch.object(matches_feature, "import_dimension_stats_from_excel") as parse_dimensions,
                    patch.object(data_upload, "save_season_dimension_stats") as save_dimensions,
                ):
                    raw, _record = data_upload.create_token(user, "test", "90", "all", [])
                    ctx = request_context(None, method="POST", path="/api/data-upload")
                    ctx.authorization = f"Bearer {raw}"
                    ctx.form = {
                        "competition_name": ["深圳联赛"],
                        "season_name": ["S4"],
                    }
                    ctx.files = {
                        field_name: [
                            web_app.UploadedFile(
                                filename,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                b"not-an-excel-file",
                            )
                        ]
                    }
                    statuses: list[str] = []
                    body = data_upload.handle_api(
                        ctx,
                        lambda status, _headers: statuses.append(status),
                    )

                payload = json.loads(body[0])
                self.assertEqual(statuses, ["403 Forbidden"])
                self.assertIn(expected_error, payload["error"])
                parse_matches.assert_not_called()
                parse_dimensions.assert_not_called()
                save_dimensions.assert_not_called()

    def test_read_only_account_cannot_create_upload_token(self):
        audit_user = scoped_user(
            "audit",
            SCOPE_SHENZHEN,
            ["scope_audit_view"],
        )
        ctx = request_context(audit_user, method="POST", path="/profile")
        ctx.form = {"action": ["create_upload_token"]}

        created, message, raw = data_upload.handle_profile_action(ctx, lambda *_args: None)

        self.assertFalse(created)
        self.assertEqual(raw, "")
        self.assertIn("没有比赛数据或维度数据上传权限", message)

    def test_team_claim_review_is_platform_or_scope_admin_only(self):
        shenzhen_team = {
            "team_id": "team-sz",
            "competition_name": "深圳联赛",
            "season_name": "S4",
        }
        beijing_team = {
            "team_id": "team-bj",
            "competition_name": "北京联赛",
            "season_name": "S2",
        }
        scope_admin = scoped_user(
            "scope-admin",
            SCOPE_SHENZHEN,
            is_scope_admin=True,
        )
        result_editor = scoped_user(
            "result-editor",
            SCOPE_SHENZHEN,
            ["match_result_manage"],
        )
        platform_team_manager = {
            "username": "team-manager",
            "role": "member",
            "permissions": ["team_manage"],
        }

        with patch.object(
            web_app,
            "get_competition_scope_key",
            side_effect=self.scope_key_for_competition,
        ):
            self.assertTrue(
                team_center.can_review_team_claim_request(
                    self.data,
                    scope_admin,
                    shenzhen_team,
                )
            )
            self.assertFalse(
                team_center.can_review_team_claim_request(
                    self.data,
                    scope_admin,
                    beijing_team,
                )
            )
            self.assertFalse(
                team_center.can_review_team_claim_request(
                    self.data,
                    result_editor,
                    shenzhen_team,
                )
            )
            self.assertTrue(
                team_center.can_review_team_claim_request(
                    self.data,
                    platform_team_manager,
                    beijing_team,
                )
            )

    def test_scope_admin_can_manage_players_and_teams_only_in_own_series(self):
        shenzhen_team = {
            "team_id": "team-sz",
            "name": "深圳战队",
            "competition_name": "深圳联赛",
            "season_name": "S4",
            "members": ["player-sz"],
        }
        beijing_team = {
            "team_id": "team-bj",
            "name": "北京战队",
            "competition_name": "北京联赛",
            "season_name": "S2",
            "members": ["player-bj"],
        }
        data = {
            "matches": [
                {
                    "match_id": "bj-s2-260820-01",
                    "competition_name": "北京联赛",
                    "season": "S2",
                    "players": [{"player_id": "player-shared", "team_id": "team-bj"}],
                }
            ],
            "teams": [shenzhen_team, beijing_team],
            "players": [
                {"player_id": "player-sz", "team_id": "team-sz"},
                {"player_id": "player-bj", "team_id": "team-bj"},
                {"player_id": "player-shared", "team_id": "team-sz"},
            ],
        }
        scope_admin = scoped_user(
            "scope-admin",
            SCOPE_SHENZHEN,
            is_scope_admin=True,
        )
        result_editor = scoped_user(
            "result-editor",
            SCOPE_SHENZHEN,
            ["match_result_manage"],
        )
        multi_scope_admin = {
            **scope_admin,
            "username": "multi-scope-admin",
            "scope_grants": [
                {
                    "scope_key": SCOPE_SHENZHEN,
                    "permissions": [],
                    "is_scope_admin": True,
                },
                {
                    "scope_key": SCOPE_BEIJING,
                    "permissions": [],
                    "is_scope_admin": True,
                },
            ],
        }

        with (
            patch.object(web_app, "load_validated_data", return_value=data),
            patch.object(
                web_app,
                "get_competition_scope_key",
                side_effect=self.scope_key_for_competition,
            ),
        ):
            admin_ctx = request_context(scope_admin)
            result_ctx = request_context(result_editor)
            self.assertTrue(web_app.can_manage_team(admin_ctx, shenzhen_team, None))
            self.assertTrue(web_app.can_manage_player(admin_ctx, "player-sz"))
            self.assertFalse(web_app.can_manage_team(admin_ctx, beijing_team, None))
            self.assertFalse(web_app.can_manage_player(admin_ctx, "player-bj"))
            self.assertFalse(web_app.can_manage_player(admin_ctx, "player-shared"))
            self.assertTrue(
                web_app.can_manage_player(
                    request_context(multi_scope_admin),
                    "player-shared",
                )
            )
            self.assertFalse(web_app.can_manage_team(result_ctx, shenzhen_team, None))
            self.assertFalse(web_app.can_manage_player(result_ctx, "player-sz"))

    def test_scope_admin_can_repair_completed_team_profile(self):
        team = {
            "team_id": "team-sz",
            "name": "深圳战队",
            "short_name": "深圳",
            "notes": "旧备注",
            "competition_name": "深圳联赛",
            "season_name": "S4",
            "members": [],
        }
        data = {"matches": [], "teams": [team], "players": []}
        scope_admin = scoped_user(
            "scope-admin",
            SCOPE_SHENZHEN,
            is_scope_admin=True,
        )
        ctx = request_context(scope_admin, method="POST", path="/team-center")
        ctx.form = {
            "action": ["update_team_profile"],
            "team_id": ["team-sz"],
            "short_name": ["修正简称"],
            "notes": ["修正备注"],
            "next": ["/teams/team-sz"],
        }
        statuses: list[str] = []

        with (
            patch.object(team_center_v2, "load_validated_data", return_value=data),
            patch.object(team_center_v2, "load_users", return_value=[]),
            patch.object(team_center_v2, "load_membership_requests", return_value=[]),
            patch.object(team_center_v2, "get_team_season_status", return_value="completed"),
            patch.object(web_app, "load_validated_data", return_value=data),
            patch.object(
                web_app,
                "get_competition_scope_key",
                side_effect=self.scope_key_for_competition,
            ),
            patch.object(team_center_v2, "save_repository_state", return_value=[]) as save_state,
            patch.object(team_center_v2, "audit_action"),
        ):
            team_center_v2.handle_team_center_impl(
                ctx,
                lambda status, _headers: statuses.append(status),
            )

        self.assertEqual(statuses, ["302 Found"])
        self.assertEqual(team["short_name"], "修正简称")
        self.assertEqual(team["notes"], "修正备注")
        save_state.assert_called_once()

    def test_cross_scope_claim_approval_is_rejected_before_write(self):
        target_team = {
            "team_id": "team-bj",
            "name": "北京战队",
            "competition_name": "北京联赛",
            "season_name": "S2",
            "members": [],
            "captain_player_id": None,
        }
        data = {"matches": [], "players": [], "teams": [target_team]}
        scope_admin = scoped_user(
            "scope-admin",
            SCOPE_SHENZHEN,
            is_scope_admin=True,
        )
        request = {
            "request_id": "claim-1",
            "request_type": "team_claim",
            "username": "requester",
            "target_team_id": "team-bj",
        }
        ctx = request_context(scope_admin, method="POST", path="/team-center")
        ctx.form = {
            "action": ["approve_team_claim"],
            "request_id": ["claim-1"],
        }
        statuses: list[str] = []

        with (
            patch.object(team_center_v2, "load_validated_data", return_value=data),
            patch.object(team_center_v2, "load_users", return_value=[]),
            patch.object(team_center_v2, "load_membership_requests", return_value=[request]),
            patch.object(team_center_v2, "layout", side_effect=lambda _title, body, _ctx: body),
            patch.object(team_center_v2, "save_repository_state") as save_state,
            patch.object(web_app, "get_competition_scope_key", side_effect=self.scope_key_for_competition),
        ):
            team_center_v2.handle_team_center_impl(
                ctx,
                lambda status, _headers: statuses.append(status),
            )

        self.assertEqual(statuses, ["403 Forbidden"])
        save_state.assert_not_called()


if __name__ == "__main__":
    unittest.main()
