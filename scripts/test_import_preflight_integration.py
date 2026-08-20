import tempfile
import unittest
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

import import_worker
import web_app
from web.features import matches


def build_ctx(*, path="/matches/new", method="POST", action=""):
    return web_app.RequestContext(
        method=method,
        path=path,
        query={},
        form={"action": [action]} if action else {},
        files={},
        current_user={"username": "operator", "role": "admin"},
        now_label="2026-08-20 12:00:00 中国时间",
    )


class ImportPreflightIntegrationTests(unittest.TestCase):
    def test_match_preflight_uses_an_isolated_repository_copy(self):
        ctx = build_ctx()
        data = {"matches": [{"match_id": "match-1"}], "teams": [], "players": []}

        def parse(_ctx, working_data, _upload, _group, result_metadata=None):
            working_data["matches"][0]["changed_during_preflight"] = True
            result_metadata.update(
                {
                    "matched_match_ids": ["match-1"],
                    "matched_scopes": [
                        {"competition_name": "测试赛事", "season_name": "S1"}
                    ],
                }
            )
            return working_data["matches"], "预检完成"

        with patch.object(matches, "import_matches_from_excel", side_effect=parse):
            preview, errors, _warnings, scopes = matches.preflight_match_excel_upload(
                ctx,
                data,
                web_app.UploadedFile("matches.xlsx", "application/xlsx", b"xlsx"),
                "",
            )

        self.assertEqual(errors, [])
        self.assertEqual(scopes, {"测试赛事"})
        self.assertEqual(preview["counts"]["updated_matches"], 1)
        self.assertNotIn("changed_during_preflight", data["matches"][0])

    def test_team_logo_preflight_validates_without_writing_asset_or_source_data(self):
        ctx = build_ctx()
        data = {
            "teams": [
                {
                    "team_id": "team-1",
                    "name": "测试战队",
                    "competition_name": "测试赛事",
                    "season_name": "S1",
                    "logo": "old.png",
                }
            ],
            "players": [],
            "matches": [],
        }
        upload = web_app.UploadedFile("logos.xlsx", "application/xlsx", b"xlsx")
        with (
            patch.object(matches, "read_first_available_sheet_rows", return_value=[{"team_name": "测试战队"}]),
            patch.object(matches, "read_excel_sheet_embedded_images", return_value={(2, 2): ("logo.png", b"image")}),
            patch.object(matches, "can_manage_competition_action", return_value=True),
            patch.object(matches, "validate_match_competition_selection", return_value=""),
            patch.object(matches, "validate_match_season_selection", return_value=""),
            patch.object(matches, "validate_embedded_image") as validate_image,
            patch.object(matches, "save_embedded_team_logo") as save_logo,
        ):
            preview, errors, _warnings = matches.preflight_team_logo_excel_upload(
                ctx, data, upload, "测试赛事", "S1"
            )

        self.assertEqual(errors, [])
        self.assertEqual(preview["counts"]["updated_teams"], 1)
        self.assertEqual(data["teams"][0]["logo"], "old.png")
        validate_image.assert_called_once()
        save_logo.assert_not_called()

    def test_player_zip_preflight_does_not_extract_or_write_final_photo(self):
        ctx = build_ctx()
        data = {
            "teams": [],
            "players": [{"player_id": "player-1", "display_name": "选手一", "photo": "old.png"}],
            "matches": [
                {
                    "competition_name": "测试赛事",
                    "season": "S1",
                    "players": [{"player_id": "player-1", "player_name": "选手一"}],
                }
            ],
        }
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            archive.writestr("player-1.png", b"image")
        upload = web_app.UploadedFile("photos.zip", "application/zip", buffer.getvalue())
        with (
            patch.object(matches, "can_manage_competition_action", return_value=True),
            patch.object(matches, "validate_match_competition_selection", return_value=""),
            patch.object(matches, "validate_match_season_selection", return_value=""),
            patch.object(matches, "validate_embedded_image") as validate_image,
            patch.object(matches, "save_pending_player_photo_import") as save_pending,
            patch.object(matches, "save_embedded_player_photo") as save_final,
        ):
            preview, errors, warnings = matches.preflight_player_photo_zip_upload(
                ctx, data, upload, "测试赛事", "S1"
            )

        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(preview["counts"]["matched_photos"], 1)
        self.assertEqual(data["players"][0]["photo"], "old.png")
        validate_image.assert_called_once()
        save_pending.assert_not_called()
        save_final.assert_not_called()

    def test_legacy_match_post_now_redirects_to_preflight_review(self):
        ctx = build_ctx(action="import_match_excel")
        ctx.form["group_label"] = ["A组"]
        ctx.files = {
            "match_excel_file": [
                web_app.UploadedFile("matches.xlsx", "application/xlsx", b"xlsx")
            ]
        }
        response = {}

        def start_response(status, headers):
            response["status"] = status
            response["headers"] = dict(headers)

        with (
            patch.object(matches, "load_validated_data", return_value={"matches": [], "teams": [], "players": []}),
            patch.object(matches, "validate_excel_upload", return_value=""),
            patch.object(
                matches,
                "preflight_match_excel_upload",
                return_value=(
                    {"counts": {"updated_matches": 1}, "matched_scopes": []},
                    [],
                    [],
                    {"测试赛事"},
                ),
            ),
            patch.object(matches, "create_import_upload_preflight", return_value="imp_review") as create_job,
        ):
            matches.handle_match_create(ctx, start_response)

        self.assertEqual(response["status"], "302 Found")
        self.assertEqual(
            response["headers"]["Location"],
            "/console/imports/review?job_id=imp_review",
        )
        self.assertEqual(create_job.call_args.kwargs["action"], "matches.import_excel")

    def test_batch_visibility_requires_every_scope(self):
        ctx = build_ctx()
        ctx.current_user["role"] = "event_manager"
        job = {
            "created_by": "operator",
            "action": "matches.import_excel",
            "metadata": {"permission_scope_keys": ["深圳::sd", "北京::jc"]},
        }

        def has_permission(_user, scope_key, permission_key):
            if permission_key == "scope_audit_view":
                return False
            return scope_key == "深圳::sd"

        with patch.object(matches.legacy, "user_has_scope_permission", side_effect=has_permission):
            self.assertFalse(matches.can_view_import_batch(ctx, job))

        with patch.object(matches.legacy, "user_has_scope_permission", return_value=True):
            self.assertTrue(matches.can_view_import_batch(ctx, job))

    def test_rollback_requires_platform_admin(self):
        ctx = build_ctx()
        ctx.current_user["role"] = "event_manager"
        job = {
            "metadata": {"permission_scope_keys": ["深圳::sd", "北京::jc"]},
        }
        ctx.current_user["scope_grants"] = [
            {
                "scope_key": "深圳::sd",
                "permissions": [],
                "is_scope_admin": True,
            },
            {
                "scope_key": "北京::jc",
                "permissions": [],
                "is_scope_admin": True,
            },
        ]
        self.assertFalse(matches.can_rollback_import_batch(ctx, job))

        ctx.current_user["role"] = "admin"
        self.assertTrue(matches.can_rollback_import_batch(ctx, job))

    def test_review_get_returns_404_for_missing_job(self):
        ctx = build_ctx(path="/console/imports/review", method="GET")
        ctx.query = {"job_id": ["missing"]}
        statuses = []
        with patch.object(matches, "get_preflight", return_value=None):
            matches.handle_import_preflight_review(
                ctx,
                lambda status, _headers: statuses.append(status),
            )
        self.assertEqual(statuses, ["404 Not Found"])

    def test_review_get_returns_403_for_existing_unauthorized_job(self):
        ctx = build_ctx(path="/console/imports/review", method="GET")
        ctx.current_user["role"] = "event_manager"
        ctx.query = {"job_id": ["imp-other"]}
        job = {
            "batch_id": "imp-other",
            "created_by": "other-user",
            "status": "awaiting_confirmation",
            "metadata": {
                "permission_scope_keys": ["北京::jc"],
                "preflight": {"payload": {}},
            },
        }
        statuses = []
        with (
            patch.object(matches, "get_preflight", return_value=job),
            patch.object(matches, "can_access_import_preflight", return_value=False),
        ):
            matches.handle_import_preflight_review(
                ctx,
                lambda status, _headers: statuses.append(status),
            )
        self.assertEqual(statuses, ["403 Forbidden"])


class AssetImportRollbackTests(unittest.TestCase):
    CASES = (
        (
            "team_logo",
            "run_team_logo_excel_import_job",
            "import_team_logos_from_excel",
            "assets/teams/generated-logo.png",
        ),
        (
            "player_photo",
            "run_player_photo_zip_import_job",
            "import_player_photos_from_zip",
            "assets/players/generated-photo.png",
        ),
    )

    def _run_asset_job(
        self,
        *,
        runner_name: str,
        importer_name: str,
        relative_asset_path: str,
        save_errors: list[str],
    ):
        ctx = build_ctx()
        upload = web_app.UploadedFile("assets.zip", "application/octet-stream", b"data")
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            asset_path = root_dir / relative_asset_path
            asset_path.parent.mkdir(parents=True, exist_ok=True)

            def import_assets(
                _ctx,
                _data,
                _upload,
                _competition_name,
                _season_name,
                *,
                persist_assets,
                result_metadata,
            ):
                self.assertTrue(persist_assets)
                asset_path.write_bytes(b"generated")
                result_metadata.update(
                    {
                        "_created_asset_paths": [relative_asset_path],
                        "public_count": 1,
                    }
                )
                return ([{"id": "persisted-record"}], "素材导入完成")

            update_calls = []
            audit_calls = []
            with (
                patch.object(matches, "ROOT_DIR", root_dir),
                patch.object(matches, "TEAM_UPLOAD_DIR", root_dir / "assets" / "teams"),
                patch.object(
                    matches.legacy,
                    "PLAYER_UPLOAD_DIR",
                    root_dir / "assets" / "players",
                ),
                patch.object(
                    matches,
                    "load_validated_data",
                    return_value={"matches": [], "teams": [], "players": []},
                ),
                patch.object(matches, "import_job_revision_changed", return_value=False),
                patch.object(matches, importer_name, side_effect=import_assets),
                patch.object(matches, "load_users", return_value=[]),
                patch.object(matches, "save_repository_state", return_value=save_errors),
                patch.object(
                    matches,
                    "update_import_batch",
                    side_effect=lambda *args, **kwargs: update_calls.append(
                        (deepcopy(args), deepcopy(kwargs))
                    ),
                ),
                patch.object(
                    matches,
                    "audit_action",
                    side_effect=lambda *args, **kwargs: audit_calls.append(
                        (deepcopy(args), deepcopy(kwargs))
                    ),
                ),
            ):
                getattr(matches, runner_name)(
                    ctx,
                    upload,
                    "测试赛事",
                    "S1",
                    "imp-assets",
                    expected_data_revision=7,
                )

            return asset_path.exists(), update_calls, audit_calls

    def test_database_save_failure_removes_new_generated_assets(self):
        for (
            label,
            runner_name,
            importer_name,
            relative_asset_path,
        ) in self.CASES:
            with self.subTest(asset_type=label):
                asset_exists, update_calls, audit_calls = self._run_asset_job(
                    runner_name=runner_name,
                    importer_name=importer_name,
                    relative_asset_path=relative_asset_path,
                    save_errors=["数据库保存失败"],
                )

                self.assertFalse(asset_exists)
                self.assertEqual(update_calls[-1][1]["status"], "failed")
                self.assertEqual(audit_calls, [])

    def test_success_does_not_persist_internal_created_asset_paths(self):
        for (
            label,
            runner_name,
            importer_name,
            relative_asset_path,
        ) in self.CASES:
            with self.subTest(asset_type=label):
                asset_exists, update_calls, audit_calls = self._run_asset_job(
                    runner_name=runner_name,
                    importer_name=importer_name,
                    relative_asset_path=relative_asset_path,
                    save_errors=[],
                )

                self.assertTrue(asset_exists)
                succeeded_metadata = next(
                    kwargs["metadata"]
                    for _args, kwargs in update_calls
                    if kwargs.get("status") == "succeeded"
                )
                self.assertEqual(succeeded_metadata["public_count"], 1)
                self.assertNotIn("_created_asset_paths", succeeded_metadata)
                self.assertEqual(len(audit_calls), 1)
                audit_metadata = audit_calls[0][1]["metadata"]
                self.assertEqual(audit_metadata["public_count"], 1)
                self.assertNotIn("_created_asset_paths", audit_metadata)


class ImportWorkerDispatchTests(unittest.TestCase):
    def test_worker_dispatches_all_four_preflight_actions(self):
        action_to_runner = {
            "matches.import_excel": "run_match_excel_import_job",
            "dimension.import_excel": "run_dimension_excel_import_job",
            "team_logo.import_excel": "run_team_logo_excel_import_job",
            "player_photo.import_zip": "run_player_photo_zip_import_job",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            for index, (action, runner_name) in enumerate(action_to_runner.items()):
                with self.subTest(action=action):
                    suffix = ".zip" if action == "player_photo.import_zip" else ".xlsx"
                    payload_path = Path(temp_dir) / f"payload-{index}{suffix}"
                    payload_path.write_bytes(b"payload")
                    job = {
                        "batch_id": f"imp-{index}",
                        "action": action,
                        "filename": payload_path.name,
                        "created_by": "operator",
                        "payload_path": str(payload_path),
                        "metadata": {
                            "competition_name": "测试赛事",
                            "season_name": "S1",
                            "preflight": {"confirmed_revision": 41},
                        },
                    }
                    with (
                        patch.object(import_worker, "validate_excel_upload", return_value=""),
                        patch.object(import_worker, "validate_zip_upload", return_value=""),
                        patch.object(
                            import_worker,
                            "build_worker_context",
                            return_value=SimpleNamespace(
                                current_user={"username": "operator"}
                            ),
                        ),
                        patch.object(import_worker, "reserve_data_revision", return_value=42),
                        patch.object(import_worker, "invalidate_validated_data_cache"),
                        patch.object(import_worker, "get_preflight", return_value=None),
                        patch.object(import_worker, "load_import_job_records", return_value=[]),
                        patch.object(import_worker, runner_name) as runner,
                    ):
                        import_worker.process_job(job)
                    runner.assert_called_once()
                    self.assertEqual(
                        runner.call_args.kwargs["expected_data_revision"],
                        42,
                    )

    def test_worker_marks_confirmed_job_stale_before_dispatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            payload_path = Path(temp_dir) / "payload.xlsx"
            payload_path.write_bytes(b"payload")
            job = {
                "batch_id": "imp-stale",
                "action": "matches.import_excel",
                "filename": payload_path.name,
                "created_by": "operator",
                "payload_path": str(payload_path),
                "metadata": {"preflight": {"confirmed_revision": 7}},
            }
            with (
                patch.object(import_worker, "validate_excel_upload", return_value=""),
                patch.object(
                    import_worker,
                    "build_worker_context",
                    return_value=SimpleNamespace(
                        current_user={"username": "operator"}
                    ),
                ),
                patch.object(
                    import_worker,
                    "reserve_data_revision",
                    side_effect=import_worker.RepositoryConflictError("stale"),
                ),
                patch.object(import_worker, "get_data_revision", return_value=8),
                patch.object(import_worker, "update_import_job_record") as update_job,
                patch.object(import_worker, "run_match_excel_import_job") as runner,
            ):
                import_worker.process_job(job)

            runner.assert_not_called()
            self.assertEqual(update_job.call_args.kwargs["status"], "stale")

    def test_worker_rejects_inactive_creator_before_reserving_revision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            payload_path = Path(temp_dir) / "payload.xlsx"
            payload_path.write_bytes(b"payload")
            job = {
                "batch_id": "imp-inactive",
                "action": "matches.import_excel",
                "filename": payload_path.name,
                "created_by": "disabled-operator",
                "payload_path": str(payload_path),
                "metadata": {"preflight": {"confirmed_revision": 7}},
            }
            with (
                patch.object(import_worker, "validate_excel_upload", return_value=""),
                patch.object(
                    import_worker,
                    "build_worker_context",
                    return_value=SimpleNamespace(current_user=None),
                ),
                patch.object(import_worker, "reserve_data_revision") as reserve,
                patch.object(import_worker, "update_import_job_record") as update_job,
            ):
                import_worker.process_job(job)

            reserve.assert_not_called()
            self.assertEqual(update_job.call_args.kwargs["status"], "failed")
            self.assertIn("已停用", update_job.call_args.kwargs["summary"])


if __name__ == "__main__":
    unittest.main()
