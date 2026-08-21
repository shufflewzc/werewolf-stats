from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_app
from web.features import data_upload
from web.features import matches as matches_feature


class DataUploadTokenTests(unittest.TestCase):
    def setUp(self):
        self.meta: dict[str, str] = {}
        self.user = {"username": "manager", "role": "admin", "active": True}
        self.data = {
            "matches": [
                {"match_id": "a-s1-260817-01", "competition_name": "赛事A", "season": "S1", "played_on": "2026-08-17", "round": 2, "game_no": 1, "stage": "regular_season", "table_label": "1号房"},
                {"match_id": "a-s2-260817-01", "competition_name": "赛事A", "season": "S2", "played_on": "2026-08-17", "round": 1, "game_no": 1, "stage": "regular_season", "table_label": "1号房"},
            ]
        }
        def mutate_json_meta(key, fallback, mutator, **_kwargs):
            raw = self.meta.get(key, "")
            try:
                current = json.loads(raw) if raw else fallback
            except json.JSONDecodeError:
                current = fallback
            next_value, result = mutator(current)
            if next_value is not None:
                self.meta[key] = json.dumps(next_value, ensure_ascii=False)
            return result

        self.patches = [
            patch.object(data_upload.legacy, "load_meta_value", side_effect=lambda key: self.meta.get(key)),
            patch.object(
                data_upload.legacy,
                "save_meta_value",
                side_effect=lambda key, value, **_kwargs: self.meta.__setitem__(key, value),
            ),
            patch.object(data_upload, "mutate_json_meta_value", side_effect=mutate_json_meta),
            patch.object(data_upload.legacy, "load_users", return_value=[self.user]),
            patch.object(data_upload.legacy, "load_validated_data", return_value=self.data),
            patch.object(data_upload.legacy, "can_manage_matches", return_value=True),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def context(self, token: str):
        return web_app.RequestContext(
            method="GET", path="/api/data-upload/targets", query={}, form={}, files={},
            current_user=None, now_label=web_app.china_now_label(), authorization=f"Bearer {token}",
        )

    def test_raw_token_is_only_returned_and_hash_is_stored(self):
        raw, record = data_upload.create_token(self.user, "测试", "90", "all", [], "赛场电脑")
        self.assertTrue(raw.startswith(data_upload.TOKEN_PREFIX))
        self.assertNotEqual(record["token_hash"], raw)
        self.assertEqual(record["note"], "赛场电脑")
        self.assertNotIn(raw, self.meta[data_upload.TOKEN_META_KEY])
        user, authenticated, error = data_upload.authenticate(self.context(raw))
        self.assertEqual(error, "")
        self.assertEqual(user["username"], "manager")
        self.assertEqual(authenticated["token_id"], record["token_id"])

    def test_token_metadata_is_manageable_without_revealing_raw_token(self):
        raw, record = data_upload.create_token(self.user, "原名称", "90", "all", [], "原备注")
        original_hash = record["token_hash"]
        self.assertTrue(data_upload.update_token("manager", record["token_id"], "赛场 Windows", "京师 S2 专用"))
        updated = data_upload.load_tokens()[0]
        self.assertEqual(updated["name"], "赛场 Windows")
        self.assertEqual(updated["note"], "京师 S2 专用")
        self.assertEqual(updated["token_hash"], original_hash)
        self.assertFalse(data_upload.update_token("其他用户", record["token_id"], "不应更新", ""))

        ctx = self.context(raw)
        ctx.current_user = self.user
        revealed_page = data_upload.token_panel(ctx, raw)
        managed_page = data_upload.token_panel(ctx)
        self.assertEqual(revealed_page.count(raw), 1)
        self.assertNotIn(raw, managed_page)
        self.assertNotIn(original_hash, managed_page)
        self.assertIn("京师 S2 专用", managed_page)
        self.assertIn("保存名称与备注", managed_page)
        self.assertIn("撤销令牌", managed_page)

    def test_selected_scope_and_revoke(self):
        target = data_upload.available_targets(self.user)[0]
        raw, record = data_upload.create_token(self.user, "限制", "never", "selected", [target["scope_key"]])
        self.assertTrue(data_upload.target_allowed(record, target["competition_name"], target["season_name"]))
        self.assertFalse(data_upload.target_allowed(record, "赛事A", "不存在"))
        self.assertTrue(data_upload.revoke_token("manager", record["token_id"]))
        self.assertIn("已撤销", data_upload.authenticate(self.context(raw))[2])

    def test_expired_token_is_rejected(self):
        raw, record = data_upload.create_token(self.user, "过期", "30", "all", [])
        tokens = data_upload.load_tokens()
        tokens[0]["expires_at"] = (web_app.china_now() - timedelta(seconds=1)).isoformat()
        data_upload.save_tokens(tokens)
        self.assertIn("已过期", data_upload.authenticate(self.context(raw))[2])

    def test_inactive_token_owner_is_rejected(self):
        raw, _record = data_upload.create_token(self.user, "停用账号", "90", "all", [])
        self.user["active"] = False

        user, record, error = data_upload.authenticate(self.context(raw))

        self.assertIsNone(user)
        self.assertIsNone(record)
        self.assertIn("账号已停用", error)

    def test_stale_authentication_read_cannot_overwrite_revocation(self):
        raw, record = data_upload.create_token(self.user, "并发撤销", "90", "all", [])
        stale_tokens = json.loads(json.dumps(data_upload.load_tokens(), ensure_ascii=False))
        self.assertTrue(data_upload.revoke_token("manager", record["token_id"]))

        with patch.object(data_upload, "load_tokens", return_value=stale_tokens):
            user, authenticated, error = data_upload.authenticate(self.context(raw))

        self.assertIsNone(user)
        self.assertIsNone(authenticated)
        self.assertIn("已撤销", error)
        self.assertTrue(json.loads(self.meta[data_upload.TOKEN_META_KEY])[0]["revoked_at"])

    def test_targets_api_uses_bearer_scope(self):
        target = data_upload.available_targets(self.user)[0]
        raw, _ = data_upload.create_token(self.user, "限制", "90", "selected", [target["scope_key"]])
        ctx = self.context(raw)
        response_status = []
        body = data_upload.handle_api(ctx, lambda status, headers: response_status.append(status))
        payload = json.loads(body[0])
        self.assertEqual(response_status, ["200 OK"])
        self.assertEqual(len(payload["targets"]), 1)
        self.assertEqual(payload["targets"][0]["scope_key"], target["scope_key"])

    def test_matches_api_filters_selected_season(self):
        raw, _ = data_upload.create_token(self.user, "全部", "90", "all", [])
        ctx = self.context(raw)
        ctx.path = "/api/data-upload/matches"
        ctx.query = {"competition_name": ["赛事A"], "season_name": ["S2"]}
        body = data_upload.handle_api(ctx, lambda _status, _headers: None)
        payload = json.loads(body[0])
        self.assertEqual([item["match_id"] for item in payload["matches"]], ["a-s2-260817-01"])

    def test_job_status_is_scoped_to_creating_token(self):
        raw, record = data_upload.create_token(self.user, "全部", "90", "all", [])
        batch = {"batch_id": "imp_test", "status": "succeeded", "summary": "完成", "completed_at": "now", "metadata": {"upload_token_id": record["token_id"]}}
        ctx = self.context(raw)
        ctx.path = "/api/data-upload/jobs/imp_test"
        with patch.object(data_upload.legacy, "load_import_batches", return_value=[batch]):
            body = data_upload.handle_api(ctx, lambda _status, _headers: None)
        self.assertEqual(json.loads(body[0])["status"], "succeeded")

        other_raw, _ = data_upload.create_token(self.user, "另一个令牌", "90", "all", [])
        other_ctx = self.context(other_raw)
        other_ctx.path = "/api/data-upload/jobs/imp_test"
        with patch.object(data_upload.legacy, "load_import_batches", return_value=[batch]):
            other_body = data_upload.handle_api(other_ctx, lambda _status, _headers: None)
        self.assertIn("没有找到", json.loads(other_body[0])["error"])

    def test_match_upload_must_belong_to_selected_target(self):
        raw, _ = data_upload.create_token(self.user, "全部", "90", "all", [])
        ctx = self.context(raw)
        ctx.method = "POST"
        ctx.path = "/api/data-upload"
        ctx.form = {
            "competition_name": ["赛事A"],
            "season_name": ["S2"],
            "request_id": ["scope-check"],
        }
        ctx.files = {
            "match_file": [web_app.UploadedFile("match.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"fake")],
        }

        with (
            patch.object(matches_feature, "validate_excel_upload", return_value=""),
            patch.object(
                matches_feature,
                "preflight_match_excel_upload",
                return_value=(
                    {
                        "summary": "预检完成",
                        "matched_scopes": [
                            {"competition_name": "赛事A", "season_name": "S1"}
                        ],
                    },
                    [],
                    [],
                    {"赛事A"},
                ),
            ),
        ):
            body = data_upload.handle_api(ctx, lambda _status, _headers: None)
        self.assertIn("与当前上传目标", json.loads(body[0])["results"]["match"]["message"])

    def test_match_is_preflighted_confirmed_and_queued_with_target_metadata(self):
        raw, record = data_upload.create_token(self.user, "全部", "90", "all", [])
        ctx = self.context(raw)
        ctx.method = "POST"
        ctx.path = "/api/data-upload"
        ctx.form = {
            "competition_name": ["赛事A"],
            "season_name": ["S2"],
            "request_id": ["match-first"],
        }
        ctx.files = {
            "match_file": [web_app.UploadedFile("match.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"fake")],
        }

        preview = {
            "summary": "预检完成",
            "counts": {"updated_matches": 1},
            "matched_scopes": [
                {"competition_name": "赛事A", "season_name": "S2"}
            ],
        }

        with (
            patch.object(matches_feature, "validate_excel_upload", return_value=""),
            patch.object(
                matches_feature,
                "preflight_match_excel_upload",
                return_value=(preview, [], ["预检提醒"], {"赛事A"}),
            ) as inspect_match,
            patch.object(data_upload.legacy, "load_import_batches", return_value=[]),
            patch.object(
                matches_feature,
                "create_import_upload_preflight",
                return_value="imp_match",
            ) as create_preflight,
            patch.object(data_upload, "confirm_preflight") as confirm,
            patch.object(data_upload.legacy, "create_import_batch") as legacy_create,
            patch.object(data_upload.legacy, "audit_action"),
        ):
            payload = json.loads(data_upload.handle_api(ctx, lambda _status, _headers: None)[0])

        self.assertEqual(payload["results"]["match"]["status"], "queued")
        inspect_match.assert_called_once_with(ctx, self.data, ctx.files["match_file"][0], "")
        self.assertEqual(create_preflight.call_args.kwargs["action"], "matches.import_excel")
        self.assertEqual(create_preflight.call_args.kwargs["preview"], preview)
        self.assertEqual(create_preflight.call_args.kwargs["warnings"], ["预检提醒"])
        self.assertEqual(create_preflight.call_args.kwargs["competition_names"], {"赛事A"})
        metadata = create_preflight.call_args.kwargs["action_metadata"]
        self.assertEqual(metadata["upload_token_id"], record["token_id"])
        self.assertEqual(
            (metadata["competition_name"], metadata["season_name"]),
            ("赛事A", "S2"),
        )
        confirm.assert_called_once()
        self.assertEqual(confirm.call_args.args, ("imp_match",))
        self.assertEqual(confirm.call_args.kwargs["actor"], "manager")
        legacy_create.assert_not_called()

    def test_double_file_upload_is_rejected_in_favor_of_match_first(self):
        raw, _ = data_upload.create_token(self.user, "全部", "90", "all", [])
        ctx = self.context(raw)
        ctx.method = "POST"
        ctx.path = "/api/data-upload"
        ctx.form = {
            "competition_name": ["赛事A"],
            "season_name": ["S2"],
            "request_id": ["preflight-check"],
        }
        upload = web_app.UploadedFile("data.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"fake")
        ctx.files = {"match_file": [upload], "dimension_file": [upload]}

        body = data_upload.handle_api(ctx, lambda _status, _headers: None)
        results = json.loads(body[0])["results"]
        self.assertEqual(results["dimension"]["status"], "failed")
        self.assertEqual(results["match"]["status"], "failed")
        self.assertIn("先单独导入 match", results["match"]["message"])

    def test_dimension_requires_owned_successful_match_batch(self):
        raw, record = data_upload.create_token(self.user, "全部", "90", "all", [])
        ctx = self.context(raw)
        ctx.method = "POST"
        ctx.path = "/api/data-upload"
        ctx.form = {
            "competition_name": ["赛事A"],
            "season_name": ["S2"],
            "request_id": ["dimension-after-match"],
            "match_batch_id": ["imp_owned"],
        }
        upload = web_app.UploadedFile("dimension.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"fake")
        ctx.files = {"dimension_file": [upload]}
        successful_batch = {
            "batch_id": "imp_owned",
            "status": "succeeded",
            "metadata": {
                "upload_token_id": record["token_id"],
                "competition_name": "赛事A",
                "season_name": "S2",
                "dimension_ready": True,
                "matched_match_ids": ["a-s2-260817-01"],
            },
        }

        with (
            patch.object(matches_feature, "validate_excel_upload", return_value=""),
            patch.object(data_upload.legacy, "load_import_batches", return_value=[]),
        ):
            rejected = json.loads(data_upload.handle_api(ctx, lambda _status, _headers: None)[0])
        self.assertIn("必须等待", rejected["results"]["dimension"]["message"])

        with (
            patch.object(matches_feature, "validate_excel_upload", return_value=""),
            patch.object(data_upload.legacy, "load_import_batches", return_value=[successful_batch]),
            patch.object(matches_feature, "import_dimension_stats_from_excel", return_value=([{"player_id": "p1"}], [{"team_id": "t1"}], "dimension 完成")),
            patch.object(data_upload, "save_season_dimension_stats") as save_dimension,
            patch.object(data_upload.legacy, "invalidate_validated_data_cache"),
            patch.object(data_upload.legacy, "audit_action"),
        ):
            accepted = json.loads(data_upload.handle_api(ctx, lambda _status, _headers: None)[0])
        self.assertEqual(accepted["results"]["dimension"]["status"], "succeeded")
        save_dimension.assert_called_once()

    def test_dimension_rejects_succeeded_batch_before_player_confirmation(self):
        raw, record = data_upload.create_token(self.user, "全部", "90", "all", [])
        ctx = self.context(raw)
        ctx.method = "POST"
        ctx.path = "/api/data-upload"
        ctx.form = {
            "competition_name": ["赛事A"],
            "season_name": ["S2"],
            "request_id": ["dimension-before-confirmation"],
            "match_batch_id": ["imp_unconfirmed"],
        }
        ctx.files = {
            "dimension_file": [
                web_app.UploadedFile(
                    "dimension.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    b"fake",
                )
            ]
        }
        batch = {
            "batch_id": "imp_unconfirmed",
            "status": "succeeded",
            "metadata": {
                "upload_token_id": record["token_id"],
                "competition_name": "赛事A",
                "season_name": "S2",
                "dimension_ready": False,
                "matched_match_ids": ["a-s2-260817-01"],
            },
        }

        with (
            patch.object(matches_feature, "validate_excel_upload", return_value=""),
            patch.object(data_upload.legacy, "load_import_batches", return_value=[batch]),
            patch.object(matches_feature, "import_dimension_stats_from_excel") as importer,
            patch.object(data_upload, "save_season_dimension_stats") as save_dimension,
        ):
            response_status = []
            payload = json.loads(
                data_upload.handle_api(
                    ctx,
                    lambda status, _headers: response_status.append(status),
                )[0]
            )

        self.assertEqual(response_status, ["409 Conflict"])
        self.assertIn("完成比赛和新选手确认", payload["results"]["dimension"]["message"])
        importer.assert_not_called()
        save_dimension.assert_not_called()

    def test_dimension_reloads_confirmed_players_before_parsing_and_uses_revision(self):
        raw, record = data_upload.create_token(self.user, "全部", "90", "all", [])
        ctx = self.context(raw)
        ctx.method = "POST"
        ctx.path = "/api/data-upload"
        ctx.form = {
            "competition_name": ["赛事A"],
            "season_name": ["S2"],
            "request_id": ["dimension-fresh-confirmed-data"],
            "match_batch_id": ["imp_confirmed"],
        }
        ctx.files = {
            "dimension_file": [
                web_app.UploadedFile(
                    "dimension.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    b"fake",
                )
            ]
        }
        stale_data = {
            **self.data,
            "players": [],
            "teams": [],
            "_data_revision": 7,
        }
        fresh_data = {
            "matches": [
                {
                    "match_id": "a-s2-260817-01",
                    "competition_name": "赛事A",
                    "season": "S2",
                    "played_on": "2026-08-17",
                    "round": 1,
                    "game_no": 1,
                    "stage": "regular_season",
                    "table_label": "1号房",
                    "players": [{"player_id": "p-new", "team_id": "team-a"}],
                }
            ],
            "players": [
                {
                    "player_id": "p-new",
                    "display_name": "新选手",
                    "team_id": "team-a",
                }
            ],
            "teams": [
                {
                    "team_id": "team-a",
                    "name": "战队A",
                    "competition_name": "赛事A",
                    "season_name": "S2",
                    "members": ["p-new"],
                }
            ],
            "_data_revision": 8,
        }
        batch = {
            "batch_id": "imp_confirmed",
            "status": "succeeded",
            "metadata": {
                "upload_token_id": record["token_id"],
                "competition_name": "赛事A",
                "season_name": "S2",
                "dimension_ready": True,
                "matched_match_ids": ["a-s2-260817-01"],
            },
        }

        with (
            patch.object(matches_feature, "validate_excel_upload", return_value=""),
            patch.object(data_upload.legacy, "load_import_batches", return_value=[batch]),
            patch.object(
                data_upload.legacy,
                "load_validated_data",
                side_effect=[stale_data, fresh_data],
            ),
            patch.object(
                matches_feature,
                "import_dimension_stats_from_excel",
                return_value=([{"player_id": "p-new"}], [], "dimension 完成"),
            ) as importer,
            patch.object(data_upload, "save_season_dimension_stats") as save_dimension,
            patch.object(data_upload.legacy, "invalidate_validated_data_cache"),
            patch.object(data_upload.legacy, "audit_action"),
        ):
            payload = json.loads(
                data_upload.handle_api(ctx, lambda _status, _headers: None)[0]
            )

        self.assertEqual(payload["results"]["dimension"]["status"], "succeeded")
        self.assertIs(importer.call_args.args[1], fresh_data)
        save_dimension.assert_called_once_with(
            [{"player_id": "p-new"}],
            [],
            expected_revision=8,
        )

    def test_dimension_revision_conflict_returns_409_without_success(self):
        raw, record = data_upload.create_token(self.user, "全部", "90", "all", [])
        ctx = self.context(raw)
        ctx.method = "POST"
        ctx.path = "/api/data-upload"
        ctx.form = {
            "competition_name": ["赛事A"],
            "season_name": ["S2"],
            "request_id": ["dimension-revision-conflict"],
            "match_batch_id": ["imp_conflict"],
        }
        ctx.files = {
            "dimension_file": [
                web_app.UploadedFile(
                    "dimension.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    b"fake",
                )
            ]
        }
        batch = {
            "batch_id": "imp_conflict",
            "status": "succeeded",
            "metadata": {
                "upload_token_id": record["token_id"],
                "competition_name": "赛事A",
                "season_name": "S2",
                "dimension_ready": True,
                "matched_match_ids": ["a-s2-260817-01"],
            },
        }

        with (
            patch.object(matches_feature, "validate_excel_upload", return_value=""),
            patch.object(data_upload.legacy, "load_import_batches", return_value=[batch]),
            patch.object(
                matches_feature,
                "import_dimension_stats_from_excel",
                return_value=([{"player_id": "p1"}], [], "dimension 完成"),
            ),
            patch.object(
                data_upload,
                "save_season_dimension_stats",
                side_effect=data_upload.RepositoryConflictError("版本变化"),
            ),
            patch.object(data_upload.legacy, "invalidate_validated_data_cache"),
        ):
            response_status = []
            payload = json.loads(
                data_upload.handle_api(
                    ctx,
                    lambda status, _headers: response_status.append(status),
                )[0]
            )

        self.assertEqual(response_status, ["409 Conflict"])
        self.assertEqual(payload["results"]["dimension"]["status"], "failed")
        self.assertIn("本次未写入", payload["results"]["dimension"]["message"])

    def test_player_photo_upload_is_preflighted_and_queued_for_owned_target(self):
        raw, record = data_upload.create_token(self.user, "头像匹配器", "90", "all", [])
        ctx = self.context(raw)
        ctx.method = "POST"
        ctx.path = "/api/data-upload/player-photos"
        ctx.form = {
            "competition_name": ["赛事A"],
            "season_name": ["S2"],
            "request_id": ["photo-upload-1"],
        }
        ctx.files = {
            "player_photo_zip": [
                web_app.UploadedFile("matched-player-photos.zip", "application/zip", b"fake")
            ],
        }
        preview = {
            "summary": "头像预检完成",
            "counts": {"matched_photos": 3, "unmatched_photos": 0, "conflicts": 0},
            "matched_scopes": [
                {"competition_name": "赛事A", "season_name": "S2"}
            ],
        }

        with (
            patch.object(data_upload.legacy, "can_manage_competition_action", return_value=True),
            patch.object(matches_feature, "validate_zip_upload", return_value=""),
            patch.object(
                matches_feature,
                "preflight_player_photo_zip_upload",
                return_value=(preview, [], []),
            ),
            patch.object(
                matches_feature,
                "create_import_upload_preflight",
                return_value="imp_photos",
            ) as create_preflight,
            patch.object(data_upload, "confirm_preflight") as confirm,
            patch.object(data_upload.legacy, "audit_action"),
        ):
            response_status = []
            body = data_upload.handle_api(
                ctx,
                lambda status, _headers: response_status.append(status),
            )

        payload = json.loads(body[0])
        self.assertEqual(response_status, ["200 OK"])
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["batch_id"], "imp_photos")
        self.assertIn("3 张头像", payload["message"])
        action_metadata = create_preflight.call_args.kwargs["action_metadata"]
        self.assertEqual(action_metadata["upload_token_id"], record["token_id"])
        self.assertEqual(create_preflight.call_args.kwargs["action"], "player_photo.import_zip")
        confirm.assert_called_once()
        self.assertFalse(data_upload.legacy.save_meta_value.call_args.kwargs["bump_revision"])

    def test_player_photo_upload_retries_a_stale_cached_batch(self):
        raw, record = data_upload.create_token(self.user, "头像匹配器", "90", "all", [])
        identity = f"{record['token_id']}:photo-upload-retry"
        self.meta[data_upload.REQUEST_META_KEY] = json.dumps(
            {
                identity: {
                    "status": "queued",
                    "batch_id": "imp_stale",
                    "message": "旧任务",
                }
            },
            ensure_ascii=False,
        )
        ctx = self.context(raw)
        ctx.method = "POST"
        ctx.path = "/api/data-upload/player-photos"
        ctx.form = {
            "competition_name": ["赛事A"],
            "season_name": ["S2"],
            "request_id": ["photo-upload-retry"],
        }
        ctx.files = {
            "player_photo_zip": [
                web_app.UploadedFile("matched-player-photos.zip", "application/zip", b"fake")
            ],
        }
        preview = {
            "summary": "头像预检完成",
            "counts": {"matched_photos": 2},
            "matched_scopes": [
                {"competition_name": "赛事A", "season_name": "S2"}
            ],
        }

        with (
            patch.object(data_upload.legacy, "can_manage_competition_action", return_value=True),
            patch.object(
                data_upload.legacy,
                "load_import_batches",
                return_value=[{"batch_id": "imp_stale", "status": "stale"}],
            ),
            patch.object(matches_feature, "validate_zip_upload", return_value=""),
            patch.object(
                matches_feature,
                "preflight_player_photo_zip_upload",
                return_value=(preview, [], []),
            ),
            patch.object(
                matches_feature,
                "create_import_upload_preflight",
                return_value="imp_retry",
            ) as create_preflight,
            patch.object(data_upload, "confirm_preflight"),
            patch.object(data_upload.legacy, "audit_action"),
        ):
            body = data_upload.handle_api(ctx, lambda _status, _headers: None)

        payload = json.loads(body[0])
        self.assertEqual(payload["batch_id"], "imp_retry")
        create_preflight.assert_called_once()
        saved_requests = json.loads(self.meta[data_upload.REQUEST_META_KEY])
        self.assertEqual(saved_requests[identity]["batch_id"], "imp_retry")

    def test_player_photo_upload_requires_season_asset_permission(self):
        raw, _record = data_upload.create_token(self.user, "头像匹配器", "90", "all", [])
        ctx = self.context(raw)
        ctx.method = "POST"
        ctx.path = "/api/data-upload/player-photos"
        ctx.form = {
            "competition_name": ["赛事A"],
            "season_name": ["S2"],
        }
        ctx.files = {
            "player_photo_zip": [
                web_app.UploadedFile("matched-player-photos.zip", "application/zip", b"fake")
            ],
        }

        def scoped_permission(_user, _data, _competition, permission):
            return permission == "match_import_manage"

        with patch.object(
            data_upload.legacy,
            "can_manage_competition_action",
            side_effect=scoped_permission,
        ):
            response_status = []
            body = data_upload.handle_api(
                ctx,
                lambda status, _headers: response_status.append(status),
            )

        self.assertEqual(response_status, ["403 Forbidden"])
        self.assertIn("头像上传权限", json.loads(body[0])["error"])


class MatchImportPersistenceConfirmationTests(unittest.TestCase):
    def confirmed_data(self):
        return {
            "matches": [
                {
                    "match_id": "match-1",
                    "competition_name": "赛事A",
                    "season": "S2",
                    "players": [
                        {"player_id": "player-new", "team_id": "team-a"},
                        {"player_id": "NPC", "team_id": "team-a"},
                    ],
                }
            ],
            "players": [
                {
                    "player_id": "player-new",
                    "display_name": "新选手",
                    "team_id": "team-a",
                }
            ],
            "teams": [
                {
                    "team_id": "team-a",
                    "name": "战队A",
                    "competition_name": "赛事A",
                    "season_name": "S2",
                    "members": ["player-new"],
                }
            ],
        }

    def test_completed_match_import_requires_persisted_player(self):
        data = self.confirmed_data()
        data["players"] = []

        errors = matches_feature.validate_completed_match_import(
            data,
            ["match-1"],
            "赛事A",
            "S2",
        )

        self.assertTrue(any("尚未创建" in error for error in errors))

    def test_completed_match_import_accepts_resolvable_player_and_team(self):
        errors = matches_feature.validate_completed_match_import(
            self.confirmed_data(),
            ["match-1"],
            "赛事A",
            "S2",
        )

        self.assertEqual(errors, [])

    def test_match_job_waits_for_persistence_confirmation_before_succeeding(self):
        ctx = web_app.RequestContext(
            method="POST",
            path="/api/data-upload",
            query={},
            form={},
            files={},
            current_user={"username": "manager", "role": "admin", "active": True},
            now_label="2026-08-21 12:00:00",
        )
        source_data = {
            "_data_revision": 7,
            "matches": [
                {
                    "match_id": "match-1",
                    "competition_name": "赛事A",
                    "season": "S2",
                    "players": [],
                }
            ],
            "players": [],
            "teams": [
                {
                    "team_id": "team-a",
                    "name": "战队A",
                    "competition_name": "赛事A",
                    "season_name": "S2",
                    "members": [],
                }
            ],
        }
        imported_player = {
            "player_id": "player-new",
            "display_name": "新选手",
            "team_id": "team-a",
        }
        imported_match = {
            "match_id": "match-1",
            "competition_name": "赛事A",
            "season": "S2",
            "players": [{"player_id": "player-new", "team_id": "team-a"}],
        }
        confirmed_data = self.confirmed_data()
        confirmed_data["_data_revision"] = 9
        events = []

        def import_match(_ctx, data, _upload, _label, result_metadata=None):
            data["players"].append(imported_player)
            data["teams"][0]["members"].append("player-new")
            result_metadata["matched_match_ids"] = ["match-1"]
            return [imported_match], "match 完成"

        def record_update(_batch_id, **kwargs):
            events.append(("status", kwargs["status"], kwargs.get("metadata") or {}))

        def confirm_persistence(_expectation):
            events.append(("confirm", "", {}))
            return confirmed_data, []

        upload = web_app.UploadedFile(
            "match.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            b"fake",
        )
        with (
            patch.object(matches_feature, "load_validated_data", return_value=source_data),
            patch.object(matches_feature, "import_matches_from_excel", side_effect=import_match),
            patch.object(matches_feature, "canonicalize_match_ids", side_effect=lambda rows: (rows, "match-1")),
            patch.object(matches_feature, "load_users", return_value=[]),
            patch.object(matches_feature, "ensure_placeholder_players_for_matches", return_value=[]),
            patch.object(matches_feature, "ensure_placeholder_users_for_player_ids", return_value=[]),
            patch.object(matches_feature.legacy, "save_imported_matches_state", return_value=[]),
            patch.object(
                matches_feature,
                "wait_for_match_import_confirmation",
                side_effect=confirm_persistence,
            ),
            patch.object(matches_feature, "update_import_batch", side_effect=record_update),
            patch.object(matches_feature, "audit_action"),
        ):
            matches_feature.run_match_excel_import_job(
                ctx,
                upload,
                "赛事A / S2",
                "imp-confirm",
            )

        self.assertEqual(events[0][0], "confirm")
        self.assertEqual(events[1][0:2], ("status", "succeeded"))
        self.assertTrue(events[1][2]["dimension_ready"])
        self.assertEqual(events[1][2]["match_confirmed_revision"], 9)
        self.assertEqual(events[1][2]["created_players"], 1)

    def test_match_job_does_not_succeed_when_confirmation_fails(self):
        ctx = web_app.RequestContext(
            method="POST",
            path="/api/data-upload",
            query={},
            form={},
            files={},
            current_user={"username": "manager", "role": "admin", "active": True},
            now_label="2026-08-21 12:00:00",
        )
        source_data = {
            "matches": [{"match_id": "match-1", "competition_name": "赛事A", "season": "S2", "players": []}],
            "players": [],
            "teams": [],
        }
        updates = []
        upload = web_app.UploadedFile(
            "match.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            b"fake",
        )
        with (
            patch.object(matches_feature, "load_validated_data", return_value=source_data),
            patch.object(
                matches_feature,
                "import_matches_from_excel",
                side_effect=lambda _ctx, _data, _upload, _label, result_metadata=None: (
                    result_metadata.update({"matched_match_ids": ["match-1"]})
                    or source_data["matches"],
                    "match 完成",
                ),
            ),
            patch.object(matches_feature, "canonicalize_match_ids", side_effect=lambda rows: (rows, "match-1")),
            patch.object(matches_feature, "load_users", return_value=[]),
            patch.object(matches_feature, "ensure_placeholder_players_for_matches", return_value=[]),
            patch.object(matches_feature, "ensure_placeholder_users_for_player_ids", return_value=[]),
            patch.object(matches_feature.legacy, "save_imported_matches_state", return_value=[]),
            patch.object(
                matches_feature,
                "wait_for_match_import_confirmation",
                return_value=(None, ["选手 player-new 尚未创建"]),
            ),
            patch.object(
                matches_feature,
                "update_import_batch",
                side_effect=lambda _batch_id, **kwargs: updates.append(kwargs),
            ),
            patch.object(matches_feature, "audit_action"),
        ):
            matches_feature.run_match_excel_import_job(
                ctx,
                upload,
                "赛事A / S2",
                "imp-unconfirmed",
            )

        self.assertEqual([item["status"] for item in updates], ["failed"])
        self.assertFalse(updates[0]["metadata"]["dimension_ready"])
        self.assertIn("dimension 未上传", updates[0]["summary"])


if __name__ == "__main__":
    unittest.main()
