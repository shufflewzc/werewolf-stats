import os
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import import_worker
import sqlite_store
import web_app
from web_app import (
    build_placeholder_player,
    get_client_ip,
    resolve_match_award_player_ids,
    validate_match_awards,
)


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

    def test_import_job_update_preserves_or_clears_payload_path(self):
        batch_id = "imp_20260727_140000_update"
        sqlite_store.create_import_job_record(
            {
                "batch_id": batch_id,
                "action": "matches.import_excel",
                "label": "状态更新测试",
                "status": "queued",
                "created_at": "2026-07-27 14:00:00 中国时间",
                "created_by": "admin",
                "payload_path": "/tmp/import.xlsx",
                "metadata": {"background": True},
            },
            snapshot_json='{"data":{},"users":[]}',
        )
        sqlite_store.claim_import_job("worker-1")

        sqlite_store.update_import_job_record(
            batch_id,
            status="succeeded",
            summary="导入完成",
            completed_at="2026-07-27 14:01:00 中国时间",
            metadata={"created_matches": 6},
        )

        updated = sqlite_store.load_import_job_records()[0]
        self.assertEqual(updated["status"], "succeeded")
        self.assertEqual(updated["payload_path"], "/tmp/import.xlsx")
        self.assertEqual(updated["locked_at_epoch"], 0)
        self.assertEqual(updated["locked_by"], "")
        self.assertEqual(updated["metadata"]["created_matches"], 6)

        sqlite_store.update_import_job_record(
            batch_id,
            status="succeeded",
            payload_path="",
        )

        self.assertEqual(
            sqlite_store.load_import_job_records()[0]["payload_path"],
            "",
        )

    def test_import_history_cleanup_removes_expired_staged_payload(self):
        payload_dir = sqlite_store.DB_PATH.parent / "import-jobs"
        payload_dir.mkdir(parents=True, exist_ok=True)
        payload_path = payload_dir / "expired.xlsx"
        payload_path.write_bytes(b"expired")
        sqlite_store.create_import_job_record(
            {
                "batch_id": "imp_expired_payload",
                "action": "matches.import_excel",
                "label": "过期暂存文件",
                "filename": payload_path.name,
                "status": "failed",
                "created_at": "2026-07-01 10:00:00 中国时间",
                "created_by": "admin",
                "payload_path": str(payload_path),
                "metadata": {},
            },
            snapshot_json='{"data":{},"users":[]}',
        )
        with sqlite_store.connect_write_db() as connection:
            connection.execute(
                "UPDATE import_snapshots SET created_at_epoch = 1 WHERE job_id = ?",
                ("imp_expired_payload",),
            )

        result = sqlite_store.cleanup_import_history(
            retention_days=1,
            keep_latest=1,
            now_epoch=200000,
        )

        self.assertEqual(result["deleted_import_jobs"], 1)
        self.assertEqual(result["deleted_payload_files"], 1)
        self.assertFalse(payload_path.exists())

    def test_placeholder_player_includes_star_player_default(self):
        player = build_placeholder_player(
            "player-newcomer",
            "team-newcomer",
            "测试赛事",
            "S1",
        )

        self.assertIn("is_star_player", player)
        self.assertIs(player["is_star_player"], False)

    def test_failed_import_job_keeps_payload_for_retry(self):
        batch_id = "imp_20260727_150000_retry"
        payload_path = Path(self.temp_dir.name) / "retry.xlsx"
        payload_path.write_bytes(b"retry")
        sqlite_store.create_import_job_record(
            {
                "batch_id": batch_id,
                "action": "matches.import_excel",
                "label": "失败重试测试",
                "filename": payload_path.name,
                "status": "running",
                "created_at": "2026-07-27 15:00:00 中国时间",
                "created_by": "admin",
                "payload_path": str(payload_path),
                "metadata": {},
            },
            snapshot_json='{"data":{},"users":[]}',
        )
        job = sqlite_store.load_import_job_records()[0]

        def mark_failed(_ctx, _upload, _group_label, job_id):
            sqlite_store.update_import_job_record(
                job_id,
                status="failed",
                summary="测试失败",
            )

        with patch.object(
            import_worker,
            "build_worker_context",
            return_value=object(),
        ), patch.object(
                import_worker,
                "run_match_excel_import_job",
                side_effect=mark_failed,
        ):
            import_worker.process_job(job)

        refreshed = sqlite_store.load_import_job_records()[0]
        self.assertEqual(refreshed["status"], "failed")
        self.assertEqual(refreshed["payload_path"], str(payload_path))
        self.assertTrue(payload_path.is_file())

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
            "account_create": True,
        }
        data = sqlite_store.load_repository_data()
        sqlite_store.save_repository_data(data, [user])
        user.pop("account_create", None)
        sqlite_store.save_session("session-token", "admin")
        refreshed_data = sqlite_store.load_repository_data()

        sqlite_store.save_repository_data(refreshed_data, [user])

        self.assertEqual(
            sqlite_store.load_session_username("session-token"),
            "admin",
        )

    def test_inactive_account_cannot_receive_a_new_session(self):
        sqlite_store.save_users(
            [
                {
                    "username": "inactive-user",
                    "display_name": "停用账号",
                    "password_salt": "salt",
                    "password_hash": "hash",
                    "active": False,
                    "player_id": None,
                    "linked_player_ids": [],
                    "manager_scope_keys": [],
                    "permissions": [],
                    "role": "member",
                    "account_create": True,
                }
            ]
        )

        with self.assertRaises(sqlite_store.RepositoryConflictError):
            sqlite_store.save_session("inactive-session", "inactive-user")

        self.assertIsNone(
            sqlite_store.load_session_username("inactive-session")
        )

    def test_stale_password_check_cannot_create_session_after_reset(self):
        user = {
            "username": "password-user",
            "display_name": "密码账号",
            "password_salt": "old-salt",
            "password_hash": "old-hash",
            "active": True,
            "player_id": None,
            "linked_player_ids": [],
            "manager_scope_keys": [],
            "permissions": [],
            "role": "member",
            "account_create": True,
        }
        sqlite_store.save_users([user])
        stale_etag = sqlite_store.build_user_authorization_etag(
            sqlite_store.load_users()[0]
        )
        reset_user = {
            **sqlite_store.load_users()[0],
            "password_salt": "new-salt",
            "password_hash": "new-hash",
            "account_password_write": True,
        }
        sqlite_store.save_users([reset_user])

        with self.assertRaises(sqlite_store.RepositoryConflictError):
            sqlite_store.save_session(
                "stale-password-session",
                "password-user",
                expected_user_authorization_etag=stale_etag,
            )

        self.assertIsNone(
            sqlite_store.load_session_username("stale-password-session")
        )

    def test_repository_state_validation_runs_before_any_persistence(self):
        invalid_data = {
            "guilds": [],
            "teams": [
                {
                    "team_id": "team-invalid",
                    "name": "无效战队",
                    "short_name": "无效",
                    "logo": "assets/teams/default.svg",
                    "active": True,
                    "founded_on": "2026-08-20",
                    "competition_name": "测试赛事",
                    "season_name": "S1",
                    "guild_id": "",
                    "captain_player_id": None,
                    "members": ["missing-player"],
                    "stage_groups": [],
                    "notes": "",
                }
            ],
            "players": [],
            "matches": [],
        }
        users = [
            {
                "username": "admin",
                "role": "admin",
            }
        ]

        with patch.object(web_app, "save_repository_data") as persist:
            errors = web_app.save_repository_state(invalid_data, users)

        self.assertTrue(errors)
        persist.assert_not_called()

    def test_repository_state_rejects_guild_reference_from_stale_user_snapshot(self):
        stale_data = {
            "guilds": [
                {
                    "guild_id": "guild-stale",
                    "name": "旧公会",
                    "short_name": "旧",
                    "logo": "assets/guilds/default.svg",
                    "active": True,
                    "founded_on": "2026-08-20",
                    "leader_username": "retired",
                    "manager_usernames": [],
                    "honors": [],
                    "notes": "",
                }
            ],
            "teams": [],
            "players": [],
            "matches": [],
        }
        stale_users = [{"username": "retired", "role": "member"}]
        current_users = [{"username": "keeper", "role": "member"}]

        with (
            patch.object(web_app, "get_data_revision", return_value=7),
            patch.object(web_app, "load_users", return_value=current_users),
            patch.object(web_app, "save_repository_data") as persist,
        ):
            errors = web_app.save_repository_state(stale_data, stale_users)

        self.assertTrue(
            any("unknown username 'retired'" in error for error in errors),
            errors,
        )
        persist.assert_not_called()

    def test_repository_state_without_revision_pins_current_revision_before_save(self):
        data = {"guilds": [], "teams": [], "players": [], "matches": []}

        with (
            patch.object(web_app, "get_data_revision", return_value=11),
            patch.object(web_app, "load_users", return_value=[]),
            patch.object(web_app, "save_repository_data") as persist,
        ):
            errors = web_app.save_repository_state(data, [])

        self.assertEqual(errors, [])
        persisted_data = persist.call_args.args[0]
        self.assertEqual(persisted_data["_data_revision"], 11)
        self.assertNotIn("_data_revision", data)

    def test_match_award_refs_are_persisted_as_player_ids(self):
        match = {
            "players": [
                {
                    "player_id": "player-winner",
                    "player_name": "赢家",
                    "camp": "werewolves",
                },
                {
                    "player_id": "player-loser",
                    "player_name": "输家",
                    "camp": "villagers",
                },
            ],
            "winning_camp": "werewolves",
            "mvp_player_id": "",
            "svp_player_id": "",
            "scapegoat_player_id": "",
            "mvp_player_ref": "0",
            "svp_player_ref": "1",
            "scapegoat_player_ref": "1",
            "mvp_player_name": "",
            "svp_player_name": "",
            "scapegoat_player_name": "",
        }

        self.assertEqual(validate_match_awards(match), "")
        resolve_match_award_player_ids(match)

        self.assertEqual(match["mvp_player_id"], "player-winner")
        self.assertEqual(match["svp_player_id"], "player-loser")
        self.assertEqual(match["scapegoat_player_id"], "player-loser")

    def test_match_award_resolution_keeps_explicit_ids_and_legacy_names(self):
        match = {
            "players": [
                {
                    "player_id": "player-winner",
                    "player_name": "赢家",
                    "camp": "werewolves",
                },
                {
                    "player_id": "player-loser",
                    "player_name": "输家",
                    "camp": "villagers",
                },
            ],
            "mvp_player_id": "player-winner",
            "svp_player_id": "",
            "scapegoat_player_id": "",
            "mvp_player_ref": "",
            "svp_player_ref": "",
            "scapegoat_player_ref": "",
            "mvp_player_name": "",
            "svp_player_name": "输家",
            "scapegoat_player_name": "输家",
        }

        resolve_match_award_player_ids(match)

        self.assertEqual(match["mvp_player_id"], "player-winner")
        self.assertEqual(match["svp_player_id"], "player-loser")
        self.assertEqual(match["scapegoat_player_id"], "player-loser")


if __name__ == "__main__":
    unittest.main()
