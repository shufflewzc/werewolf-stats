import os
import tempfile
import unittest
from pathlib import Path

import import_preflight
import sqlite_store


class ImportPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = sqlite_store.DB_PATH
        self.previous_database_url = os.environ.pop("DATABASE_URL", None)
        self.previous_postgres_writes = os.environ.pop(
            "ENABLE_POSTGRES_WRITES", None
        )
        self.previous_postgres_reads = os.environ.pop(
            "ENABLE_POSTGRES_READS", None
        )
        self.root = Path(self.temp_dir.name)
        self.payload_dir = self.root / "payloads"
        sqlite_store.DB_PATH = self.root / "runtime.db"
        sqlite_store.ensure_database()
        with sqlite_store.connect_db() as connection:
            connection.execute(
                "INSERT INTO app_meta (meta_key, meta_value) VALUES ('initialized', '1')"
            )

    def tearDown(self):
        sqlite_store.DB_PATH = self.previous_db_path
        if self.previous_database_url is not None:
            os.environ["DATABASE_URL"] = self.previous_database_url
        if self.previous_postgres_writes is not None:
            os.environ["ENABLE_POSTGRES_WRITES"] = self.previous_postgres_writes
        if self.previous_postgres_reads is not None:
            os.environ["ENABLE_POSTGRES_READS"] = self.previous_postgres_reads
        self.temp_dir.cleanup()

    def create_job(self, **overrides):
        values = {
            "action": "matches.import_excel",
            "label": "比赛数据预检",
            "filename": "matches.xlsx",
            "created_by": "operator",
            "payload_data": b"workbook-content",
            "payload_dir": self.payload_dir,
            "payload": {"counts": {"updated": 2}},
            "required_scope_permissions": {
                "广东::shenda": ["match_upload"],
                "北京::jingcheng": ["match_upload", "match_result_edit"],
            },
            "data_revision": sqlite_store.get_data_revision(),
            "created_at": "2026-08-20 09:00:00 中国时间",
            "job_id": "imp_test_preflight",
        }
        values.update(overrides)
        return import_preflight.create_preflight(**values)

    def test_create_records_preview_payload_without_repository_mutation(self):
        before_revision = sqlite_store.get_data_revision()
        with sqlite_store.connect_read_db() as connection:
            before_matches = connection.execute(
                "SELECT COUNT(*) AS total FROM matches"
            ).fetchone()["total"]

        job_id = self.create_job(
            summary="<b>预检\x00完成</b>   等待确认",
            warnings=["日期列为空\x07", "日期列为空\x07"],
            metadata={"request_id": "request-1"},
        )

        self.assertEqual(job_id, "imp_test_preflight")
        job = import_preflight.get_preflight(job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "awaiting_confirmation")
        self.assertEqual(job["summary"], "预检完成 等待确认")
        self.assertEqual(job["metadata"]["request_id"], "request-1")
        preflight = job["metadata"]["preflight"]
        self.assertEqual(preflight["payload"]["counts"]["updated"], 2)
        self.assertEqual(preflight["warnings"], ["日期列为空"])
        self.assertEqual(
            preflight["permission_scope_keys"],
            ["北京::jingcheng", "广东::shenda"],
        )
        self.assertTrue(Path(job["payload_path"]).is_file())
        self.assertEqual(sqlite_store.get_data_revision(), before_revision)
        with sqlite_store.connect_read_db() as connection:
            after_matches = connection.execute(
                "SELECT COUNT(*) AS total FROM matches"
            ).fetchone()["total"]
        self.assertEqual(after_matches, before_matches)

    def test_zip_payload_and_arbitrary_content_type_are_preserved(self):
        job_id = self.create_job(
            filename="icons.zip",
            payload_data=b"PK\x03\x04zip-content",
            content_type="application/zip",
        )

        job = import_preflight.get_preflight(job_id)
        self.assertTrue(job["payload_path"].endswith(".zip"))
        self.assertEqual(
            Path(job["payload_path"]).read_bytes(), b"PK\x03\x04zip-content"
        )
        self.assertEqual(job["metadata"]["content_type"], "application/zip")
        self.assertEqual(
            job["metadata"]["preflight"]["payload_suffix"], ".zip"
        )

    def test_confirm_rechecks_every_scope_and_only_queues(self):
        before_revision = sqlite_store.get_data_revision()
        job_id = self.create_job()
        checked = []

        def permission_check(actor, scope_key, permission_key):
            checked.append((actor, scope_key, permission_key))
            return True

        confirmed = import_preflight.confirm_preflight(
            job_id,
            actor="operator",
            permission_check=permission_check,
            revision_getter=lambda: before_revision,
            now_label="2026-08-20 09:01:00 中国时间",
        )

        self.assertEqual(confirmed["status"], "queued")
        self.assertEqual(len(checked), 3)
        self.assertEqual(
            confirmed["metadata"]["preflight"]["confirmed_by"], "operator"
        )
        self.assertEqual(sqlite_store.get_data_revision(), before_revision)
        with sqlite_store.connect_read_db() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) AS total FROM matches").fetchone()[
                    "total"
                ],
                0,
            )

    def test_permission_is_all_or_nothing_and_lists_all_denials(self):
        job_id = self.create_job()

        def permission_check(_actor, scope_key, permission_key):
            return scope_key == "广东::shenda" and permission_key == "match_upload"

        with self.assertRaises(import_preflight.PreflightPermissionError) as raised:
            import_preflight.confirm_preflight(
                job_id,
                actor="operator",
                permission_check=permission_check,
                revision_getter=sqlite_store.get_data_revision,
            )

        self.assertEqual(
            raised.exception.denied,
            [
                {
                    "scope_key": "北京::jingcheng",
                    "permission_key": "match_result_edit",
                },
                {
                    "scope_key": "北京::jingcheng",
                    "permission_key": "match_upload",
                },
            ],
        )
        self.assertEqual(
            import_preflight.get_preflight(job_id)["status"],
            "awaiting_confirmation",
        )

    def test_blocking_validation_error_prevents_queue(self):
        job_id = self.create_job(validation_errors=["比赛编号不存在"])

        with self.assertRaises(import_preflight.PreflightValidationError) as raised:
            import_preflight.confirm_preflight(
                job_id,
                actor="operator",
                permission_check=lambda *_args: True,
                revision_getter=sqlite_store.get_data_revision,
            )

        self.assertEqual(raised.exception.errors, ["比赛编号不存在"])
        self.assertEqual(
            import_preflight.get_preflight(job_id)["status"],
            "awaiting_confirmation",
        )

    def test_revision_change_marks_job_stale_instead_of_queueing(self):
        old_revision = sqlite_store.get_data_revision()
        job_id = self.create_job(data_revision=old_revision)
        sqlite_store.bump_data_revision()

        with self.assertRaises(import_preflight.PreflightStaleError) as raised:
            import_preflight.confirm_preflight(
                job_id,
                actor="operator",
                permission_check=lambda *_args: True,
                revision_getter=sqlite_store.get_data_revision,
                now_label="2026-08-20 09:02:00 中国时间",
            )

        self.assertEqual(raised.exception.expected_revision, old_revision)
        self.assertEqual(raised.exception.current_revision, old_revision + 1)
        stale = import_preflight.get_preflight(job_id)
        self.assertEqual(stale["status"], "stale")
        self.assertFalse(stale["metadata"]["preflight"]["can_confirm"])

    def test_creator_check_fails_closed_and_supports_explicit_override(self):
        job_id = self.create_job()

        with self.assertRaises(import_preflight.PreflightCreatorError):
            import_preflight.confirm_preflight(
                job_id,
                actor="another-user",
                permission_check=lambda *_args: True,
                revision_getter=sqlite_store.get_data_revision,
            )

        confirmed = import_preflight.confirm_preflight(
            job_id,
            actor="platform-admin",
            creator_check=lambda actor, _creator, _job: actor == "platform-admin",
            permission_check=lambda *_args: True,
            revision_getter=sqlite_store.get_data_revision,
        )
        self.assertEqual(confirmed["status"], "queued")

    def test_cancel_clears_and_deletes_payload(self):
        job_id = self.create_job()
        payload_path = Path(import_preflight.get_preflight(job_id)["payload_path"])
        self.assertTrue(payload_path.is_file())

        cancelled = import_preflight.cancel_preflight(
            job_id,
            actor="operator",
            permission_check=lambda *_args: True,
            revision_getter=sqlite_store.get_data_revision,
            now_label="2026-08-20 09:03:00 中国时间",
        )

        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["payload_path"], "")
        self.assertFalse(payload_path.exists())
        self.assertEqual(
            cancelled["metadata"]["preflight"]["cancelled_by"], "operator"
        )

    def test_duplicate_confirmation_is_rejected(self):
        job_id = self.create_job()
        import_preflight.confirm_preflight(
            job_id,
            actor="operator",
            permission_check=lambda *_args: True,
            revision_getter=sqlite_store.get_data_revision,
        )

        with self.assertRaises(import_preflight.PreflightTransitionError):
            import_preflight.confirm_preflight(
                job_id,
                actor="operator",
                permission_check=lambda *_args: True,
                revision_getter=sqlite_store.get_data_revision,
            )

    def test_worker_revision_reservation_allows_only_one_confirmed_job(self):
        confirmed_revision = sqlite_store.get_data_revision()

        reserved_revision = sqlite_store.reserve_data_revision(confirmed_revision)

        self.assertEqual(reserved_revision, confirmed_revision + 1)
        with self.assertRaises(sqlite_store.RepositoryConflictError):
            sqlite_store.reserve_data_revision(confirmed_revision)

    def test_dimension_save_advances_and_can_guard_repository_revision(self):
        current_revision = sqlite_store.get_data_revision()

        sqlite_store.save_season_dimension_stats(
            [],
            [],
            expected_revision=current_revision,
        )

        self.assertEqual(sqlite_store.get_data_revision(), current_revision + 1)
        with self.assertRaises(sqlite_store.RepositoryConflictError):
            sqlite_store.save_season_dimension_stats(
                [],
                [],
                expected_revision=current_revision,
            )


if __name__ == "__main__":
    unittest.main()
