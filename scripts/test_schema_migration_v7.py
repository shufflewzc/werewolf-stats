import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import check_runtime_schema
import migrate_sqlite_to_postgres
import sqlite_store
import web_app


ROOT = Path(__file__).resolve().parents[1]
POSTGRES_SCHEMA_PATH = ROOT / "scripts" / "postgres_schema.sql"
DEPLOY_SCRIPT_PATH = ROOT / "scripts" / "deploy_update.sh"
GRANULAR_SCOPE_PERMISSIONS = (
    "competition_catalog_manage",
    "competition_season_manage",
    "match_schedule_manage",
    "match_result_manage",
    "match_import_manage",
    "dimension_data_manage",
    "season_asset_manage",
    "prediction_manage",
    "scope_audit_view",
)


class PostgresV7ScopeMigrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema_sql = POSTGRES_SCHEMA_PATH.read_text(encoding="utf-8")
        start = schema_sql.index("DO $scope_grants_v7$")
        end = schema_sql.index("$scope_grants_v7$;", start) + len("$scope_grants_v7$;")
        cls.migration_sql = schema_sql[start:end]

    def test_invalid_and_non_array_legacy_json_are_rejected_safely(self):
        self.assertEqual(
            self.migration_sql.count("WHEN invalid_text_representation THEN"),
            2,
        )
        self.assertIn(
            "jsonb_typeof(parsed_scopes) IS DISTINCT FROM 'array'",
            self.migration_sql,
        )
        self.assertIn(
            "jsonb_typeof(parsed_permissions) IS DISTINCT FROM 'array'",
            self.migration_sql,
        )
        self.assertIn(
            "jsonb_typeof(scope_element) IS DISTINCT FROM 'string'",
            self.migration_sql,
        )
        self.assertNotIn("users.permissions_json::JSONB", self.migration_sql)
        self.assertNotIn(
            "jsonb_array_elements_text(users.manager_scope_keys_json::JSONB)",
            self.migration_sql,
        )

    def test_direct_granular_keys_and_legacy_match_manage_are_both_mapped(self):
        for permission_key in GRANULAR_SCOPE_PERMISSIONS:
            self.assertIn(f"'{permission_key}'", self.migration_sql)
        self.assertIn(
            "parsed_permissions ? candidate.permission_key",
            self.migration_sql,
        )
        self.assertIn(
            "candidate.inherit_match_manage",
            self.migration_sql,
        )
        self.assertIn(
            "parsed_permissions ? 'match_manage'",
            self.migration_sql,
        )

    def test_existing_explicit_grant_wins_and_scope_is_normalized(self):
        self.assertIn(
            "ON CONFLICT (username, scope_key) DO NOTHING",
            self.migration_sql,
        )
        self.assertIn(
            "normalized_scope := region_name || '::' || series_slug",
            self.migration_sql,
        )
        self.assertIn(
            "substring(raw_scope FROM 1 FOR separator_at - 1)",
            self.migration_sql,
        )
        self.assertIn(
            "substring(raw_scope FROM separator_at + 2)",
            self.migration_sql,
        )
        self.assertNotIn("substr(raw_scope FROM", self.migration_sql)


class DeploymentRollbackContractTests(unittest.TestCase):
    def test_failed_deploy_restarts_web_and_import_worker(self):
        deploy_script = DEPLOY_SCRIPT_PATH.read_text(encoding="utf-8")
        rollback = deploy_script[
            deploy_script.index("rollback_on_error()") : deploy_script.index(
                "trap rollback_on_error"
            )
        ]
        self.assertIn('systemctl restart "$SERVICE_NAME"', rollback)
        self.assertIn('systemctl restart "$IMPORT_WORKER_SERVICE"', rollback)


class CustomSQLiteV6MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.source_path = Path(self.temp_dir.name) / "v6-backup.db"
        connection = sqlite3.connect(self.source_path)
        connection.row_factory = sqlite3.Row
        try:
            sqlite_store.create_schema(connection)
            connection.execute(
                """
                INSERT INTO users (
                    username, display_name, password_salt, password_hash, active,
                    manager_scope_keys_json, permissions_json, role
                )
                VALUES (?, ?, ?, ?, 1, ?, ?, 'event_manager')
                """,
                (
                    "legacy-manager",
                    "Legacy Manager",
                    "salt",
                    "hash",
                    json.dumps([" 深圳 :: league "]),
                    json.dumps(
                        ["competition_season_manage", "match_import_manage"]
                    ),
                ),
            )
            connection.execute("DROP TABLE user_scope_grants")
            connection.execute(
                """
                INSERT INTO app_meta (meta_key, meta_value)
                VALUES ('schema_version', '6')
                ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
                """
            )
            connection.commit()
        finally:
            connection.close()
        self.original_bytes = self.source_path.read_bytes()

    def tearDown(self):
        self.temp_dir.cleanup()

    def assert_original_source_unchanged(self):
        self.assertEqual(self.source_path.read_bytes(), self.original_bytes)
        with closing(sqlite3.connect(self.source_path)) as connection:
            table = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name = 'user_scope_grants'
                """
            ).fetchone()
            version = connection.execute(
                "SELECT meta_value FROM app_meta WHERE meta_key = 'schema_version'"
            ).fetchone()
        self.assertIsNone(table)
        self.assertEqual(version[0], "6")

    def test_custom_v6_source_is_upgraded_on_disposable_copy(self):
        prepared_path = None
        with migrate_sqlite_to_postgres.prepared_sqlite_source(
            self.source_path
        ) as prepared:
            prepared_path = prepared
            self.assertNotEqual(prepared.resolve(), self.source_path.resolve())
            with closing(
                migrate_sqlite_to_postgres.sqlite_connection(prepared)
            ) as connection:
                version = connection.execute(
                    "SELECT meta_value FROM app_meta WHERE meta_key = 'schema_version'"
                ).fetchone()[0]
                grant = connection.execute(
                    """
                    SELECT scope_key, permissions_json
                    FROM user_scope_grants
                    WHERE username = 'legacy-manager'
                    """
                ).fetchone()
            self.assertEqual(version, "7")
            self.assertEqual(grant["scope_key"], "深圳::league")
            self.assertEqual(
                json.loads(grant["permissions_json"]),
                ["competition_season_manage", "match_import_manage"],
            )
            self.assert_original_source_unchanged()

        self.assertIsNotNone(prepared_path)
        self.assertFalse(prepared_path.exists())
        self.assert_original_source_unchanged()

    def test_dry_run_accepts_v6_source_without_modifying_backup(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = migrate_sqlite_to_postgres.main(
                ["--sqlite-db", str(self.source_path)]
            )

        self.assertEqual(result, 0)
        self.assertIn("- user_scope_grants: 1", output.getvalue())
        self.assert_original_source_unchanged()


class RuntimeSchemaContractTests(unittest.TestCase):
    def test_scope_grants_table_is_required_by_cli_and_readyz(self):
        self.assertIn(
            "user_scope_grants",
            check_runtime_schema.REQUIRED_RUNTIME_TABLES,
        )
        self.assertIn("user_scope_grants", web_app.READYZ_TABLES)

    def test_runtime_cli_rejects_database_without_scope_grants_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "missing-scope-grants.db"
            with closing(sqlite3.connect(database_path)) as connection:
                connection.row_factory = sqlite3.Row
                sqlite_store.create_schema(connection)
                connection.execute(
                    """
                    INSERT INTO app_meta (meta_key, meta_value)
                    VALUES ('initialized', '1')
                    ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
                    """
                )
                connection.execute("DROP TABLE user_scope_grants")
                connection.commit()

            @contextmanager
            def fake_connect_runtime_db(_database_url=None):
                with closing(sqlite3.connect(database_path)) as connection:
                    connection.row_factory = sqlite3.Row
                    yield connection

            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch.object(
                check_runtime_schema,
                "runtime_database_summary",
                return_value={"backend": "sqlite", "database": str(database_path)},
            ), patch.object(
                check_runtime_schema,
                "connect_runtime_db",
                side_effect=fake_connect_runtime_db,
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                result = check_runtime_schema.main([])

        self.assertEqual(result, 1)
        self.assertIn("缺少表：user_scope_grants", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
