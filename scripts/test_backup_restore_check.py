import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backup_restore_check as subject


class BackupRestoreCheckTests(unittest.TestCase):
    def test_postgres_backup_archives_assets_with_same_label(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            asset_path = output_dir / "assets-20260820-010203.tar.gz"

            def fake_archive(path: Path) -> bool:
                self.assertEqual(path, asset_path)
                path.write_bytes(b"archive")
                return True

            with (
                patch.object(subject, "timestamp_label", return_value="20260820-010203"),
                patch.object(subject, "require_command", side_effect=lambda name: name),
                patch.object(subject, "runtime_table_counts", return_value={name: 0 for name in subject.CHECK_TABLES}),
                patch.object(subject, "run_command"),
                patch.object(subject, "archive_assets", side_effect=fake_archive) as archive,
                patch.object(subject, "verify_asset_archive", return_value=7) as verify,
            ):
                subject.check_postgres_backup("postgresql://example/db", "", output_dir, 14)

            archive.assert_called_once_with(asset_path)
            verify.assert_called_once_with(asset_path)

    def test_postgres_no_assets_skips_archive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(subject, "timestamp_label", return_value="20260820-010203"),
                patch.object(subject, "require_command", side_effect=lambda name: name),
                patch.object(subject, "runtime_table_counts", return_value={name: 0 for name in subject.CHECK_TABLES}),
                patch.object(subject, "run_command"),
                patch.object(subject, "archive_assets") as archive,
            ):
                subject.check_postgres_backup(
                    "postgresql://example/db",
                    "",
                    Path(temp_dir),
                    14,
                    no_assets=True,
                )

            archive.assert_not_called()

    def test_prune_postgres_backups_prunes_database_and_assets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            for label in ("20260820-010201", "20260820-010202", "20260820-010203"):
                (output_dir / f"postgres-{label}.dump").write_bytes(b"db")
                (output_dir / f"assets-{label}.tar.gz").write_bytes(b"assets")

            subject.prune_postgres_backups(output_dir, 2)

            self.assertFalse((output_dir / "postgres-20260820-010201.dump").exists())
            self.assertFalse((output_dir / "assets-20260820-010201.tar.gz").exists())
            self.assertEqual(len(list(output_dir.glob("postgres-*.dump"))), 2)
            self.assertEqual(len(list(output_dir.glob("assets-*.tar.gz"))), 2)


if __name__ == "__main__":
    unittest.main()
