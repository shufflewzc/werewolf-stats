from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import migrate_season_dimensions as migration


class SeasonDimensionMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "source.db"
        connection = sqlite3.connect(self.db_path)
        connection.executescript(
            """
            CREATE TABLE season_player_dimension_stats (
                competition_name TEXT NOT NULL,
                season_name TEXT NOT NULL,
                played_on TEXT NOT NULL,
                player_id TEXT NOT NULL,
                team_id TEXT NOT NULL,
                seat INTEGER NOT NULL,
                metrics_json TEXT NOT NULL
            );
            CREATE TABLE season_team_dimension_stats (
                competition_name TEXT NOT NULL,
                season_name TEXT NOT NULL,
                played_on TEXT NOT NULL,
                team_id TEXT NOT NULL,
                seat INTEGER NOT NULL,
                metrics_json TEXT NOT NULL
            );
            CREATE TABLE data_revisions (
                revision_key TEXT PRIMARY KEY,
                revision INTEGER NOT NULL,
                updated_at_epoch INTEGER NOT NULL
            );
            INSERT INTO data_revisions VALUES ('repository', 17, 0);
            """
        )
        connection.executemany(
            "INSERT INTO season_player_dimension_stats VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "赛事",
                    "S1",
                    "2026-01-02",
                    "player-2",
                    "team-1",
                    2,
                    '{"daily_points": 1, "games_played": 3, "wins": 1}',
                ),
                (
                    "赛事",
                    "S1",
                    "2026-01-01",
                    "player-1",
                    "team-1",
                    1,
                    '{"daily_points": 2, "games_played": 3, "wins": 2}',
                ),
                (
                    "赛事",
                    "S2",
                    "2026-02-01",
                    "player-3",
                    "team-2",
                    1,
                    '{"daily_points": 0, "games_played": 3}',
                ),
            ],
        )
        connection.executemany(
            "INSERT INTO season_team_dimension_stats VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    "赛事",
                    "S1",
                    "2026-01-01",
                    "team-1",
                    1,
                    '{"daily_points": 2, "games_played": 3, "wins": 2}',
                ),
                (
                    "赛事",
                    "S2",
                    "2026-02-01",
                    "team-2",
                    1,
                    '{"daily_points": 0, "games_played": 3}',
                ),
            ],
        )
        connection.commit()
        connection.close()

    def test_sqlite_export_contains_only_exact_scope_and_stable_digest(self) -> None:
        players, teams, revision = migration.load_sqlite_rows(
            self.db_path, "赛事", "S1"
        )
        manifest = migration.build_manifest("赛事", "S1", revision, players, teams)
        validated_players, validated_teams, digest = migration.validate_manifest(
            manifest, "赛事", "S1"
        )

        self.assertEqual(
            [row["player_id"] for row in validated_players],
            ["player-1", "player-2"],
        )
        self.assertEqual([row["team_id"] for row in validated_teams], ["team-1"])
        self.assertEqual(manifest["source_data_revision"], 17)
        self.assertEqual(manifest["sha256"], digest)

    def test_manifest_tampering_is_rejected(self) -> None:
        players, teams, revision = migration.load_sqlite_rows(
            self.db_path, "赛事", "S1"
        )
        manifest = migration.build_manifest("赛事", "S1", revision, players, teams)
        manifest["player_rows"][0]["metrics_json"] = json.dumps(
            {"daily_points": 99, "games_played": 3, "wins": 99}
        )

        with self.assertRaisesRegex(migration.MigrationError, "SHA-256"):
            migration.validate_manifest(manifest, "赛事", "S1")

    def test_foreign_scope_row_is_rejected(self) -> None:
        player_row = {
            "competition_name": "另一个赛事",
            "season_name": "S1",
            "played_on": "2026-01-01",
            "player_id": "player-1",
            "team_id": "team-1",
            "seat": 1,
            "metrics_json": '{"daily_points": 0, "games_played": 3}',
        }

        with self.assertRaisesRegex(migration.MigrationError, "another scope"):
            migration.validate_rows(
                [player_row],
                columns=migration.PLAYER_COLUMNS,
                key_columns=migration.PLAYER_KEY_COLUMNS,
                competition="赛事",
                season="S1",
            )

    def test_expected_counts_are_hard_preconditions(self) -> None:
        with self.assertRaisesRegex(migration.MigrationError, "source count"):
            migration.require_expected_counts([{}], [], 2, 0)

    def test_explicit_player_mapping_is_applied_and_must_be_used(self) -> None:
        players, _teams, revision = migration.load_sqlite_rows(
            self.db_path, "赛事", "S1"
        )
        manifest = migration.build_manifest("赛事", "S1", revision, players, [])
        validated_players, _validated_teams, _digest = migration.validate_manifest(
            manifest, "赛事", "S1"
        )
        mapping = migration.parse_player_id_map(["player-1=player-canonical"])

        mapped = migration.apply_player_id_map(
            validated_players,
            mapping,
            competition="赛事",
            season="S1",
        )

        self.assertEqual(
            [row["player_id"] for row in mapped],
            ["player-canonical", "player-2"],
        )
        with self.assertRaisesRegex(migration.MigrationError, "unused"):
            migration.apply_player_id_map(
                validated_players,
                {"not-in-source": "player-x"},
                competition="赛事",
                season="S1",
            )

    def test_nonempty_target_expectation_is_rejected(self) -> None:
        args = argparse.Namespace(
            expect_target_player_rows=1,
            expect_target_team_rows=0,
        )

        with self.assertRaisesRegex(migration.MigrationError, "empty target"):
            migration.require_empty_target_expectation(args)

    def test_backup_must_match_hash_and_pass_pg_restore_list(self) -> None:
        backup_path = Path(self.temp_dir.name) / "backup.dump"
        backup_path.write_bytes(b"custom-postgres-backup")
        digest = hashlib.sha256(backup_path.read_bytes()).hexdigest()
        args = argparse.Namespace(
            backup_reference=str(backup_path.resolve()),
            database_url="postgresql://user@db.example/targetdb",
            expect_data_revision=441,
        )
        required_tables = (
            "audit_logs",
            "data_revisions",
            "matches",
            "match_players",
            "players",
            "teams",
            "season_player_dimension_stats",
            "season_team_dimension_stats",
        )
        toc = "; dbname: targetdb\n" + "\n".join(
            line
            for table in required_tables
            for line in (
                f"1; 0 0 TABLE public {table} owner",
                f"2; 0 0 TABLE DATA public {table} owner",
            )
        )
        toc_result = subprocess.CompletedProcess(
            args=["pg_restore", "--list", str(backup_path)],
            returncode=0,
            stdout=toc,
            stderr="",
        )
        revision_result = subprocess.CompletedProcess(
            args=["pg_restore", "--data-only", "--table=data_revisions"],
            returncode=0,
            stdout=(
                "COPY public.data_revisions "
                "(revision_key, revision, updated_at_epoch) FROM stdin;\n"
                "repository\t441\t0\n\\.\n"
            ),
            stderr="",
        )

        with mock.patch.object(migration.shutil, "which", return_value="/usr/bin/pg_restore"):
            with mock.patch.object(
                migration.subprocess,
                "run",
                side_effect=[toc_result, revision_result],
            ) as run_mock:
                metadata = migration.verify_backup(
                    args,
                    digest,
                    {
                        "database_name": "targetdb",
                        "server_host": "db.example",
                        "server_port": 5432,
                        "database_user": "user",
                    },
                )

        self.assertIn("--file=-", run_mock.call_args_list[1].args[0])

        self.assertEqual(metadata["sha256"], digest)
        self.assertEqual(metadata["path"], str(backup_path.resolve()))
        self.assertEqual(metadata["database_name"], "targetdb")
        self.assertEqual(metadata["data_revision"], 441)
        self.assertEqual(metadata["server_host"], "db.example")
        self.assertTrue(metadata["created_from_target_url"])
        self.assertTrue(metadata["pg_restore_list_verified"])

        with self.assertRaisesRegex(migration.MigrationError, "SHA-256 mismatch"):
            migration.verify_backup(
                args,
                "0" * 64,
                {
                    "database_name": "targetdb",
                    "server_host": "db.example",
                    "server_port": 5432,
                    "database_user": "user",
                },
            )

    def test_backup_is_created_from_target_url_without_password_in_arguments(self) -> None:
        backup_path = Path(self.temp_dir.name) / "fresh.dump"
        args = argparse.Namespace(
            backup_reference=str(backup_path.resolve()),
            database_url="postgresql://dbuser:secret@db.example:5433/targetdb?sslmode=require",
        )
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["environment"] = kwargs["env"]
            output_path = Path(command[command.index("--file") + 1])
            output_path.write_bytes(b"full-custom-archive")
            return subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch.object(migration.shutil, "which", return_value="/usr/bin/pg_dump"):
            with mock.patch.object(migration.subprocess, "run", side_effect=fake_run):
                digest, identity = migration.create_target_backup(args)

        self.assertTrue(backup_path.is_file())
        self.assertEqual(digest, hashlib.sha256(b"full-custom-archive").hexdigest())
        self.assertNotIn("secret", " ".join(captured["command"]))
        self.assertEqual(captured["environment"]["PGPASSWORD"], "secret")
        self.assertEqual(captured["environment"]["PGSSLMODE"], "require")
        self.assertEqual(identity["server_host"], "db.example")
        self.assertEqual(identity["server_port"], 5433)

        with self.assertRaisesRegex(migration.MigrationError, "already exists"):
            migration.create_target_backup(args)

    def test_data_only_backup_toc_is_rejected(self) -> None:
        toc = "; dbname: targetdb\n" + "\n".join(
            f"2; 0 0 TABLE DATA public {table} owner"
            for table in migration.REQUIRED_BACKUP_TABLES
        )

        with self.assertRaisesRegex(migration.MigrationError, "full restorable"):
            migration.validate_backup_toc(toc, "targetdb")

    def test_apply_requires_exact_approved_manifest_digest(self) -> None:
        digest = "a" * 64
        args = argparse.Namespace(apply=True, expect_manifest_sha256="")
        with self.assertRaisesRegex(migration.MigrationError, "required"):
            migration.require_manifest_pin(args, digest)

        args.expect_manifest_sha256 = "b" * 64
        with self.assertRaisesRegex(migration.MigrationError, "mismatch"):
            migration.require_manifest_pin(args, digest)

        args.expect_manifest_sha256 = digest
        migration.require_manifest_pin(args, digest)

    def test_invalid_manifest_root_and_seat_are_reported_as_migration_errors(self) -> None:
        with self.assertRaisesRegex(migration.MigrationError, "root"):
            migration.validate_manifest([], "赛事", "S1")

        row = {
            "competition_name": "赛事",
            "season_name": "S1",
            "played_on": "2026-01-01",
            "player_id": "player-1",
            "team_id": "team-1",
            "seat": "bad",
            "metrics_json": '{"daily_points": 0, "games_played": 3}',
        }
        with self.assertRaisesRegex(migration.MigrationError, "invalid seat"):
            migration.normalized_row(row, migration.PLAYER_COLUMNS)

    def test_target_participation_must_match_player_team_date_and_seat(self) -> None:
        class Cursor:
            def __init__(self, result_sets):
                self.result_sets = list(result_sets)

            def execute(self, _query, _params):
                return None

            def fetchall(self):
                return self.result_sets.pop(0)

        player_row = {
            "competition_name": "赛事",
            "season_name": "S1",
            "played_on": "2026-01-01",
            "player_id": "player-1",
            "team_id": "team-1",
            "seat": 1,
            "metrics_json": '{"games_played": 3, "daily_points": 5}',
        }
        team_row = {
            "competition_name": "赛事",
            "season_name": "S1",
            "played_on": "2026-01-01",
            "team_id": "team-1",
            "seat": 1,
            "metrics_json": '{"games_played": 3, "daily_points": 5}',
        }
        matching_cursor = Cursor(
            [
                [("2026-01-01", "player-1", "team-1", 1)],
                [("2026-01-01", "team-1", 1)],
            ]
        )

        migration.require_target_participation(
            matching_cursor,
            [player_row],
            [team_row],
            "赛事",
            "S1",
        )

        mismatched_cursor = Cursor(
            [
                [("2026-01-01", "other-player", "team-1", 1)],
                [("2026-01-01", "team-1", 2)],
            ]
        )
        with self.assertRaisesRegex(migration.MigrationError, "participation"):
            migration.require_target_participation(
                mismatched_cursor,
                [player_row],
                [team_row],
                "赛事",
                "S1",
            )


if __name__ == "__main__":
    unittest.main()
