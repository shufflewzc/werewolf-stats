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
        self.user = {"username": "manager", "role": "admin"}
        self.data = {
            "matches": [
                {"match_id": "a-s1-260817-01", "competition_name": "赛事A", "season": "S1", "played_on": "2026-08-17", "round": 2, "game_no": 1, "stage": "regular_season", "table_label": "1号房"},
                {"match_id": "a-s2-260817-01", "competition_name": "赛事A", "season": "S2", "played_on": "2026-08-17", "round": 1, "game_no": 1, "stage": "regular_season", "table_label": "1号房"},
            ]
        }
        self.patches = [
            patch.object(data_upload.legacy, "load_meta_value", side_effect=lambda key: self.meta.get(key)),
            patch.object(data_upload.legacy, "save_meta_value", side_effect=lambda key, value: self.meta.__setitem__(key, value)),
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
        raw, record = data_upload.create_token(self.user, "测试", "90", "all", [])
        self.assertTrue(raw.startswith(data_upload.TOKEN_PREFIX))
        self.assertNotEqual(record["token_hash"], raw)
        self.assertNotIn(raw, self.meta[data_upload.TOKEN_META_KEY])
        user, authenticated, error = data_upload.authenticate(self.context(raw))
        self.assertEqual(error, "")
        self.assertEqual(user["username"], "manager")
        self.assertEqual(authenticated["token_id"], record["token_id"])

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

        def import_other_scope(_ctx, _data, _upload, result_metadata=None):
            result_metadata["matched_scopes"] = [{"competition_name": "赛事A", "season_name": "S1"}]
            return self.data["matches"], "预检完成"

        with (
            patch.object(matches_feature, "validate_excel_upload", return_value=""),
            patch.object(matches_feature, "import_matches_from_excel", side_effect=import_other_scope),
        ):
            body = data_upload.handle_api(ctx, lambda _status, _headers: None)
        self.assertIn("与当前上传目标", json.loads(body[0])["results"]["match"]["message"])

    def test_unified_preflight_marks_both_files_as_not_uploaded(self):
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

        def import_selected_scope(_ctx, _data, _upload, result_metadata=None):
            result_metadata["matched_scopes"] = [{"competition_name": "赛事A", "season_name": "S2"}]
            return self.data["matches"], "预检完成"

        with (
            patch.object(matches_feature, "validate_excel_upload", return_value=""),
            patch.object(matches_feature, "import_matches_from_excel", side_effect=import_selected_scope),
            patch.object(matches_feature, "import_dimension_stats_from_excel", return_value=(None, None, "dimension 预检失败")),
        ):
            body = data_upload.handle_api(ctx, lambda _status, _headers: None)
        results = json.loads(body[0])["results"]
        self.assertEqual(results["dimension"]["status"], "failed")
        self.assertEqual(results["match"]["status"], "failed")
        self.assertIn("尚未上传", results["match"]["message"])


if __name__ == "__main__":
    unittest.main()
