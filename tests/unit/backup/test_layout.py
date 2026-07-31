"""Contract of where a backup run puts its directories."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from baudolo.backup import layout as mod


class TestVersionDirectory(unittest.TestCase):
    def test_it_creates_the_generation_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            created = mod.create_version_directory(tmp, "20260731020304")
            self.assertTrue(Path(created).is_dir())
            self.assertEqual(Path(created).name, "20260731020304")

    def test_it_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = mod.create_version_directory(tmp, "20260731")
            second = mod.create_version_directory(tmp, "20260731")
            self.assertEqual(first, second)

    def test_it_creates_missing_parents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            nested = str(Path(tmp) / "machine" / "repo")
            created = mod.create_version_directory(nested, "20260731")
            self.assertTrue(Path(created).is_dir())


class TestVolumeDirectory(unittest.TestCase):
    def test_it_nests_the_volume_under_the_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            created = mod.create_volume_directory(tmp, "postgres_data")
            self.assertEqual(Path(created).parent, Path(tmp))
            self.assertTrue(Path(created).is_dir())


class TestMachineId(unittest.TestCase):
    def test_it_takes_the_hash_without_the_filename(self) -> None:
        digest = "a" * 64
        with mock.patch.object(
            mod, "execute_shell_command", return_value=[f"{digest}  /etc/machine-id"]
        ):
            self.assertEqual(mod.get_machine_id(), digest)


if __name__ == "__main__":
    unittest.main()
