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


class DataUploadTokenTests(unittest.TestCase):
    def setUp(self):
        self.meta: dict[str, str] = {}
        self.user = {"username": "manager", "role": "admin"}
        self.data = {
            "matches": [
                {"competition_name": "赛事A", "season": "S1"},
                {"competition_name": "赛事A", "season": "S2"},
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


if __name__ == "__main__":
    unittest.main()
