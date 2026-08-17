import tempfile
import unittest
from unittest.mock import MagicMock, patch

from baudolo.restore import files as files_mod


class TestBackingStoreGuard(unittest.TestCase):
    def restore(self, inspect: str, mounted: bool) -> tuple[int, list]:
        calls = []

        def _run(cmd, **kwargs):
            calls.append(cmd)
            return MagicMock(stdout=inspect.encode())

        with (
            patch.object(files_mod, "docker_volume_exists", return_value=True),
            patch.object(files_mod.os.path, "ismount", return_value=mounted),
            patch.object(files_mod, "run", side_effect=_run),
        ):
            code = files_mod.restore_volume_files("app_data", tempfile.mkdtemp())
        return code, calls

    def rsynced(self, calls: list) -> bool:
        return any(cmd[0] == "rsync" for cmd in calls)

    def test_plain_local_volume_is_restored_unmounted(self) -> None:
        code, calls = self.restore("/var/lib/docker/volumes/a/_data|local|plain", False)
        self.assertEqual(code, 0)
        self.assertTrue(self.rsynced(calls))

    def test_volume_with_driver_options_is_refused_while_unmounted(self) -> None:
        code, calls = self.restore("/var/lib/docker/volumes/a/_data|local|opts", False)
        self.assertEqual(code, 2)
        self.assertFalse(
            self.rsynced(calls),
            "an NFS or bind volume writes under the mount and reports success",
        )

    def test_volume_with_driver_options_is_restored_once_mounted(self) -> None:
        code, calls = self.restore("/var/lib/docker/volumes/a/_data|local|opts", True)
        self.assertEqual(code, 0)
        self.assertTrue(self.rsynced(calls))

    def test_foreign_driver_is_refused_while_unmounted(self) -> None:
        code, calls = self.restore("/mnt/gluster/a|glusterfs|plain", False)
        self.assertEqual(code, 2)
        self.assertFalse(self.rsynced(calls))

    def test_an_unresolvable_mountpoint_still_fails_first(self) -> None:
        code, calls = self.restore("|local|plain", False)
        self.assertEqual(code, 2)
        self.assertFalse(self.rsynced(calls))

    def test_a_format_without_the_new_fields_is_treated_as_plain(self) -> None:
        code, calls = self.restore("/var/lib/docker/volumes/a/_data", False)
        self.assertEqual(code, 0)
        self.assertTrue(self.rsynced(calls))


if __name__ == "__main__":
    unittest.main()
