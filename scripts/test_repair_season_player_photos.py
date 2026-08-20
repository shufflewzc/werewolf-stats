import hashlib
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import repair_season_player_photos as subject


PNG = b"\x89PNG\r\n\x1a\n" + b"test-image"


def build_manifest(folder: Path, *, expected_photo: str = subject.DEFAULT_PLAYER_PHOTO):
    asset_file = "player-one-s1-123456789abc.png"
    (folder / asset_file).write_bytes(PNG)
    source_sha = hashlib.sha256(PNG).hexdigest()
    entries = [
        {
            "player_id": "player-one",
            "display_name": "One",
            "expected_photo": expected_photo,
            "source_path": "选手头像/One.png",
            "source_sha256": source_sha,
            "asset_file": asset_file,
            "new_photo": f"assets/players/uploads/{asset_file}",
        }
    ]
    manifest = {
        "version": 1,
        "competition": "赛事",
        "season": "S1",
        "source_archive": {"sha256": "a" * 64, "name": "photos.rar"},
        "entries": entries,
        "entries_sha256": subject.canonical_json_sha256(entries),
    }
    path = folder / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return path, manifest, entries


class RepairSeasonPlayerPhotosTests(unittest.TestCase):
    def test_validate_manifest_and_asset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            path, manifest, entries = build_manifest(folder)

            actual_manifest, actual_entries = subject.validate_manifest(
                path,
                folder,
                expected_sha256=subject.sha256_file(path),
                expected_count=1,
            )

            self.assertEqual(actual_manifest["competition"], manifest["competition"])
            self.assertEqual(actual_entries, entries)

    def test_manifest_sha_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            path, _, _ = build_manifest(folder)

            with self.assertRaisesRegex(subject.RepairError, "manifest SHA-256 mismatch"):
                subject.validate_manifest(path, folder, expected_sha256="0" * 64, expected_count=1)

    def test_asset_content_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            path, _, entries = build_manifest(folder)
            (folder / entries[0]["asset_file"]).write_bytes(PNG + b"changed")

            with self.assertRaisesRegex(subject.RepairError, "prepared asset SHA-256 mismatch"):
                subject.validate_manifest(
                    path,
                    folder,
                    expected_sha256=subject.sha256_file(path),
                    expected_count=1,
                )

    def test_install_assets_never_overwrites_different_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            source = folder / "source"
            target = folder / "target"
            source.mkdir()
            target.mkdir()
            _, _, entries = build_manifest(source)
            (target / entries[0]["asset_file"]).write_bytes(PNG + b"other")

            with self.assertRaisesRegex(subject.RepairError, "different content"):
                subject.install_assets(entries, source, target)

            self.assertEqual((target / entries[0]["asset_file"]).read_bytes(), PNG + b"other")

    def test_install_and_cleanup_tracks_only_new_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            source = folder / "source"
            target = folder / "target"
            source.mkdir()
            _, _, entries = build_manifest(source)

            created = subject.install_assets(entries, source, target)
            self.assertEqual(created, [target / entries[0]["asset_file"]])
            subject.cleanup_created_assets(created)
            self.assertFalse(created[0].exists())

    def test_asset_backup_rejects_unsafe_member(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            payload = folder / "payload"
            payload.write_text("bad", encoding="utf-8")
            archive_path = folder / "assets.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                archive.add(payload, arcname="../payload")

            with self.assertRaisesRegex(subject.RepairError, "unsafe paths"):
                subject.verify_asset_backup(
                    archive_path.resolve(), subject.sha256_file(archive_path)
                )

    def test_asset_backup_requires_player_uploads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            payload = folder / "payload"
            payload.write_text("ok", encoding="utf-8")
            archive_path = folder / "assets.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                archive.add(payload, arcname="assets/teams/uploads/payload")

            with self.assertRaisesRegex(subject.RepairError, "does not contain"):
                subject.verify_asset_backup(
                    archive_path.resolve(), subject.sha256_file(archive_path)
                )

    def test_database_backup_is_bound_to_database_and_revision(self):
        toc = """; dbname: production_db
1; 0 0 TABLE public audit_logs owner
2; 0 0 TABLE DATA public audit_logs owner
3; 0 0 TABLE public data_revisions owner
4; 0 0 TABLE DATA public data_revisions owner
5; 0 0 TABLE public matches owner
6; 0 0 TABLE DATA public matches owner
7; 0 0 TABLE public match_players owner
8; 0 0 TABLE DATA public match_players owner
9; 0 0 TABLE public players owner
10; 0 0 TABLE DATA public players owner
"""
        revision_sql = "COPY public.data_revisions (revision_key, revision, updated_at_epoch) FROM stdin;\nrepository\t452\t1\n\\.\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            backup = Path(temp_dir) / "backup.dump"
            backup.write_bytes(b"backup")
            with (
                patch.object(subject.shutil, "which", return_value="pg_restore"),
                patch.object(
                    subject,
                    "run_command",
                    side_effect=[
                        CompletedProcess([], 0, toc, ""),
                        CompletedProcess([], 0, revision_sql, ""),
                    ],
                ),
            ):
                metadata = subject.verify_database_backup(
                    backup.resolve(),
                    subject.sha256_file(backup),
                    "postgresql://user@example/production_db",
                    452,
                )

            self.assertEqual(metadata["database_name"], "production_db")
            self.assertEqual(metadata["data_revision"], 452)

    def test_database_backup_rejects_stale_revision(self):
        toc_lines = ["; dbname: production_db"]
        for index, table in enumerate(subject.REQUIRED_BACKUP_TABLES):
            toc_lines.append(f"{index}; 0 0 TABLE public {table} owner")
            toc_lines.append(f"{index}; 0 0 TABLE DATA public {table} owner")
        with tempfile.TemporaryDirectory() as temp_dir:
            backup = Path(temp_dir) / "backup.dump"
            backup.write_bytes(b"backup")
            with (
                patch.object(subject.shutil, "which", return_value="pg_restore"),
                patch.object(
                    subject,
                    "run_command",
                    side_effect=[
                        CompletedProcess([], 0, "\n".join(toc_lines), ""),
                        CompletedProcess([], 0, "repository\t451\t1\n", ""),
                    ],
                ),
            ):
                with self.assertRaisesRegex(subject.RepairError, "revision mismatch"):
                    subject.verify_database_backup(
                        backup.resolve(),
                        subject.sha256_file(backup),
                        "postgresql://user@example/production_db",
                        452,
                    )


if __name__ == "__main__":
    unittest.main()
