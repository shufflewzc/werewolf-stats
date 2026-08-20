from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_app
from web.features import matches


SCOPE_KEY = "深圳市::sz-league"


def make_user(*permission_keys: str) -> dict[str, object]:
    return {
        "username": "operator",
        "role": "event_manager",
        "permissions": [],
        "scope_grants_authoritative": True,
        "scope_grants": [
            {
                "scope_key": SCOPE_KEY,
                "permissions": list(permission_keys),
                "is_scope_admin": False,
            }
        ],
    }


def make_ctx(
    *,
    user: dict[str, object],
    path: str = "/console/imports/data",
    method: str = "GET",
    form: dict[str, list[str]] | None = None,
) -> web_app.RequestContext:
    return web_app.RequestContext(
        method=method,
        path=path,
        query={},
        form=form or {},
        files={},
        current_user=user,
        now_label="2026-08-20 12:00:00 中国时间",
    )


class UnifiedDataImportPageTests(unittest.TestCase):
    def test_workflow_keeps_match_first_order_visible(self):
        html = matches.build_match_dimension_upload_workflow(
            can_import_matches=True,
            can_import_dimensions=True,
        )

        self.assertLess(html.index("步骤 1"), html.index("步骤 2"))
        self.assertLess(html.index("上传比赛结果"), html.index("上传维度数据"))
        self.assertIn("等待任务显示成功", html)
        self.assertIn("不要与比赛结果同时提交", html)

    def test_unified_page_only_renders_panels_granted_to_account(self):
        common_patches = (
            patch.object(matches, "render_match_form_page", return_value="<manual></manual>"),
            patch.object(matches, "build_match_management_panel", return_value=""),
            patch.object(matches, "build_batch_create_form", return_value=""),
            patch.object(matches, "build_excel_import_panel", return_value="MATCH_PANEL"),
            patch.object(matches, "build_dimension_import_panel", return_value="DIMENSION_PANEL"),
            patch.object(matches, "build_team_logo_import_panel", return_value=""),
            patch.object(matches, "build_player_photo_import_panel", return_value=""),
            patch.object(matches, "build_import_batches_panel", return_value=""),
        )

        for item in common_patches:
            item.start()
        try:
            match_only_html = matches.get_match_create_page(
                make_ctx(user=make_user("match_import_manage"))
            )
            dimension_only_html = matches.get_match_create_page(
                make_ctx(user=make_user("dimension_data_manage"))
            )
        finally:
            for item in reversed(common_patches):
                item.stop()

        self.assertIn("比赛与维度数据上传", match_only_html)
        self.assertIn("MATCH_PANEL", match_only_html)
        self.assertNotIn("DIMENSION_PANEL", match_only_html)
        self.assertIn("DIMENSION_PANEL", dimension_only_html)
        self.assertNotIn("MATCH_PANEL", dimension_only_html)

    def test_unified_post_rejects_wrong_upload_capability_before_parsing(self):
        ctx = make_ctx(
            user=make_user("dimension_data_manage"),
            method="POST",
            form={"action": ["import_match_excel"]},
        )
        response: dict[str, object] = {}

        def start_response(status, headers):
            response["status"] = status

        with (
            patch.object(matches, "load_validated_data", return_value={}),
            patch.object(matches, "preflight_match_excel_upload") as preflight,
        ):
            body = matches.handle_match_create(ctx, start_response)

        self.assertEqual(response["status"], "403 Forbidden")
        self.assertIn("没有执行这类数据上传的权限", b"".join(body).decode("utf-8"))
        preflight.assert_not_called()


class ImportBatchSeasonDisplayTests(unittest.TestCase):
    def test_scope_labels_support_multi_season_and_legacy_metadata(self):
        self.assertEqual(
            matches.import_batch_scope_labels(
                {
                    "metadata": {
                        "matched_scopes": [
                            {"competition_name": "京城大师赛", "season_name": "S1"},
                            {"competition_name": "京城大师赛", "season_name": "S2"},
                        ]
                    }
                }
            ),
            [("京城大师赛", "S1"), ("京城大师赛", "S2")],
        )
        self.assertEqual(
            matches.import_batch_scope_labels(
                {"metadata": {"competition_name": "深大联赛", "season_name": "S4"}}
            ),
            [("深大联赛", "S4")],
        )

    def test_import_history_renders_season_for_each_batch(self):
        batches = [
            {
                "batch_id": "multi-season",
                "status": "succeeded",
                "action": "matches.import_excel",
                "metadata": {
                    "matched_scopes": [
                        {"competition_name": "京城大师赛", "season_name": "S1"},
                        {"competition_name": "京城大师赛", "season_name": "S2"},
                    ]
                },
            },
            {
                "batch_id": "dimension",
                "status": "succeeded",
                "action": "dimension.import_excel",
                "metadata": {"competition_name": "深大联赛", "season_name": "S4"},
            },
            {
                "batch_id": "legacy",
                "status": "failed",
                "action": "matches.import_excel",
                "metadata": {},
            },
        ]
        ctx = make_ctx(user={"username": "admin", "role": "admin"}, path="/console/imports")

        with patch.object(matches, "load_import_batches", return_value=batches):
            html = matches.build_import_batches_panel(ctx)

        self.assertIn("赛事 / 赛季", html)
        self.assertIn("京城大师赛", html)
        self.assertIn("S1", html)
        self.assertIn("S2", html)
        self.assertIn("深大联赛", html)
        self.assertIn("S4", html)
        self.assertIn("未记录", html)


if __name__ == "__main__":
    unittest.main()
