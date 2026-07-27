import os
import json
import tempfile
import time
import unittest
from pathlib import Path

import sqlite_store
from web_app import get_client_ip


class BackendRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = sqlite_store.DB_PATH
        self.previous_database_url = os.environ.pop("DATABASE_URL", None)
        self.previous_postgres_writes = os.environ.pop("ENABLE_POSTGRES_WRITES", None)
        self.previous_postgres_reads = os.environ.pop("ENABLE_POSTGRES_READS", None)
        sqlite_store.DB_PATH = Path(self.temp_dir.name) / "runtime.db"
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

    def test_proxy_header_is_trusted_only_from_loopback(self):
        self.assertEqual(
            get_client_ip(
                {
                    "REMOTE_ADDR": "127.0.0.1",
                    "HTTP_X_FORWARDED_FOR": "203.0.113.9, 127.0.0.1",
                }
            ),
            "203.0.113.9",
        )
        self.assertEqual(
            get_client_ip(
                {
                    "REMOTE_ADDR": "198.51.100.4",
                    "HTTP_X_FORWARDED_FOR": "203.0.113.9",
                }
            ),
            "198.51.100.4",
        )

    def test_rate_limit_and_idempotency_are_database_backed(self):
        self.assertEqual(
            sqlite_store.consume_rate_limit_bucket("ip:login", window_seconds=60)[0],
            1,
        )
        self.assertEqual(
            sqlite_store.consume_rate_limit_bucket("ip:login", window_seconds=60)[0],
            2,
        )
        self.assertTrue(
            sqlite_store.acquire_idempotency_key("fingerprint", ttl_seconds=60)
        )
        self.assertFalse(
            sqlite_store.acquire_idempotency_key("fingerprint", ttl_seconds=60)
        )

    def test_web_login_challenge_is_deleted_after_expiry_cleanup(self):
        now = int(time.time())
        sqlite_store.save_web_login_challenge_record(
            "expired-token",
            {"status": "pending", "created_at": now - 120},
            ttl_seconds=10,
        )

        result = sqlite_store.cleanup_expired_runtime_state(now_epoch=now)

        self.assertEqual(result["web_login_challenges"], 1)
        self.assertIsNone(
            sqlite_store.load_web_login_challenge_record("expired-token")
        )

    def test_repository_revision_detects_stale_writer(self):
        data = sqlite_store.load_repository_data()
        sqlite_store.bump_data_revision()

        with self.assertRaises(sqlite_store.RepositoryConflictError):
            sqlite_store.save_repository_data(data, [])

    def test_legacy_import_history_moves_out_of_app_meta(self):
        batch_id = "imp_20260727_120000_abc123"
        with sqlite_store.connect_write_db() as connection:
            connection.execute(
                "INSERT INTO app_meta(meta_key, meta_value) VALUES (?, ?)",
                (
                    "import_batches",
                    json.dumps(
                        [
                            {
                                "batch_id": batch_id,
                                "action": "matches.import_excel",
                                "label": "历史导入",
                                "status": "succeeded",
                                "created_at": "2026-07-27 12:00:00 中国时间",
                                "created_by": "admin",
                            }
                        ],
                        ensure_ascii=False,
                    ),
                ),
            )
            connection.execute(
                "INSERT INTO app_meta(meta_key, meta_value) VALUES (?, ?)",
                ("import_batch_snapshot:" + batch_id, '{"data":{},"users":[]}'),
            )

        result = sqlite_store.migrate_legacy_import_history()

        self.assertEqual(result["migrated_import_jobs"], 1)
        self.assertEqual(result["migrated_import_snapshots"], 1)
        self.assertEqual(
            sqlite_store.load_import_job_records()[0]["batch_id"],
            batch_id,
        )
        self.assertTrue(sqlite_store.load_import_snapshot_record(batch_id))
        self.assertIsNone(sqlite_store.load_meta_value("import_batches"))

    def test_import_job_claim_is_atomic(self):
        sqlite_store.create_import_job_record(
            {
                "batch_id": "imp_20260727_130000_claim",
                "action": "matches.import_excel",
                "label": "领取测试",
                "status": "queued",
                "created_at": "2026-07-27 13:00:00 中国时间",
                "created_by": "admin",
                "metadata": {},
            },
            snapshot_json='{"data":{},"users":[]}',
        )

        claimed = sqlite_store.claim_import_job("worker-1")

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["status"], "running")
        self.assertEqual(claimed["attempts"], 1)
        self.assertEqual(claimed["locked_by"], "worker-1")
        self.assertIsNone(sqlite_store.claim_import_job("worker-2"))

    def test_incremental_repository_save_preserves_active_sessions(self):
        user = {
            "username": "admin",
            "display_name": "管理员",
            "password_salt": "salt",
            "password_hash": "hash",
            "active": True,
            "player_id": None,
            "linked_player_ids": [],
            "manager_scope_keys": [],
            "permissions": [],
            "role": "admin",
        }
        data = sqlite_store.load_repository_data()
        sqlite_store.save_repository_data(data, [user])
        sqlite_store.save_session("session-token", "admin")
        refreshed_data = sqlite_store.load_repository_data()

        sqlite_store.save_repository_data(refreshed_data, [user])

        self.assertEqual(
            sqlite_store.load_session_username("session-token"),
            "admin",
        )


if __name__ == "__main__":
    unittest.main()
