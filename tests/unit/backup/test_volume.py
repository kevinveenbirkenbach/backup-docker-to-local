"""Contract of the rsync invocation that copies a volume."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from baudolo.backup import volume as mod


class TestBackupVolume(unittest.TestCase):
    def copy(self, **kwargs) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            defaults = {
                "versions_dir": tmp,
                "volume_name": "demo",
                "volume_dir": str(Path(tmp) / "gen" / "demo"),
                "authoritative": False,
                "source": "/var/lib/docker/volumes/demo/_data/",
            }
            defaults.update(kwargs)
            with mock.patch.object(mod, "execute_shell_command") as run:
                mod.backup_volume(
                    defaults.pop("versions_dir"),
                    defaults.pop("volume_name"),
                    defaults.pop("volume_dir"),
                    **defaults,
                )
            return run.call_args[0][0]

    def test_the_quick_check_pass_carries_no_checksum(self) -> None:
        self.assertNotIn("--checksum", self.copy(authoritative=False))

    def test_the_authoritative_pass_compares_by_content(self) -> None:
        self.assertIn("--checksum", self.copy(authoritative=True))

    def test_it_reads_from_the_given_source(self) -> None:
        command = self.copy(source="/snapshot/volumes/demo/_data/")
        self.assertIn("/snapshot/volumes/demo/_data/", command)

    def test_it_always_deletes_what_the_source_no_longer_has(self) -> None:
        self.assertIn("--delete", self.copy())

    def test_it_carries_no_kernel_objects_into_a_generation(self) -> None:
        self.assertIn("--no-D", self.copy())

    def test_it_keeps_no_twin_of_what_the_second_pass_replaces(self) -> None:
        command = self.copy(authoritative=True)
        self.assertEqual(command[:2], ["rsync", "-aP"])
        self.assertNotIn("--backup", command)

    def test_it_creates_the_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "gen" / "demo"
            with mock.patch.object(mod, "execute_shell_command"):
                mod.backup_volume(
                    tmp, "demo", str(dest), authoritative=False, source="/src/"
                )
            self.assertTrue((dest / "files").is_dir())

    def test_source_is_required(self) -> None:
        with self.assertRaises(TypeError):
            mod.backup_volume("/v", "demo", "/d", authoritative=False)

    def test_authoritative_is_required(self) -> None:
        with self.assertRaises(TypeError):
            mod.backup_volume("/v", "demo", "/d", source="/src/")


class TestLastBackupDir(unittest.TestCase):
    def test_it_ignores_the_generation_being_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            current = Path(tmp) / "20260101" / "demo" / "files"
            current.mkdir(parents=True)
            found = mod.get_last_backup_dir(tmp, "demo", str(current) + "/")
            self.assertIsNone(found)

    def test_it_finds_the_previous_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            older = Path(tmp) / "20260101" / "demo" / "files"
            older.mkdir(parents=True)
            current = Path(tmp) / "20260102" / "demo" / "files"
            current.mkdir(parents=True)
            found = mod.get_last_backup_dir(tmp, "demo", str(current) + "/")
            self.assertEqual(found, str(older) + "/")

    def test_a_first_run_has_no_predecessor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(mod.get_last_backup_dir(tmp, "demo", f"{tmp}/x/"))


if __name__ == "__main__":
    unittest.main()
