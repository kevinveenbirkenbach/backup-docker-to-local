"""Contract of the filesystem snapshot used to capture volumes atomically."""

from __future__ import annotations

import unittest

from baudolo.backup.shell import BackupException
from baudolo.backup.snapshot import SnapshotError, volume_snapshot


class Runner:
    def __init__(self, replies: dict[str, list[str]] | None = None) -> None:
        self.calls: list[str] = []
        self.replies = replies or {}

    def __call__(self, command: str) -> list[str]:
        self.calls.append(command)
        for prefix, reply in self.replies.items():
            if command.startswith(prefix):
                return reply
        return []


class TestBtrfs(unittest.TestCase):
    def test_it_creates_a_read_only_snapshot_inside_the_subject(self) -> None:
        run = Runner()
        with volume_snapshot("btrfs", "/var/lib/docker", "20260731", run=run):
            pass
        self.assertEqual(
            run.calls[0],
            "btrfs subvolume snapshot -r /var/lib/docker /var/lib/docker/.baudolo-20260731",
        )

    def test_it_removes_the_snapshot_afterwards(self) -> None:
        run = Runner()
        with volume_snapshot("btrfs", "/var/lib/docker", "20260731", run=run):
            pass
        self.assertEqual(run.calls[-1], "btrfs subvolume delete /var/lib/docker/.baudolo-20260731")

    def test_it_maps_a_volume_path_into_the_snapshot(self) -> None:
        run = Runner()
        with volume_snapshot("btrfs", "/var/lib/docker", "20260731", run=run) as resolve:
            self.assertEqual(
                resolve("/var/lib/docker/volumes/postgres_data/_data"),
                "/var/lib/docker/.baudolo-20260731/volumes/postgres_data/_data",
            )

    def test_it_keeps_the_trailing_slash_rsync_reads_as_contents(self) -> None:
        run = Runner()
        with volume_snapshot("btrfs", "/var/lib/docker", "20260731", run=run) as resolve:
            self.assertEqual(
                resolve("/var/lib/docker/volumes/postgres_data/_data/"),
                "/var/lib/docker/.baudolo-20260731/volumes/postgres_data/_data/",
            )

    def test_it_removes_the_snapshot_even_when_the_body_raises(self) -> None:
        run = Runner()
        with self.assertRaises(ZeroDivisionError):
            with volume_snapshot("btrfs", "/var/lib/docker", "20260731", run=run):
                raise ZeroDivisionError
        self.assertTrue(run.calls[-1].startswith("btrfs subvolume delete"))


class TestZfs(unittest.TestCase):
    def _run(self) -> Runner:
        return Runner({"zfs list": ["tank/docker"]})

    def test_it_snapshots_the_dataset_mounted_at_the_subject(self) -> None:
        run = self._run()
        with volume_snapshot("zfs", "/var/lib/docker", "20260731", run=run):
            pass
        self.assertIn("zfs snapshot tank/docker@baudolo-20260731", run.calls)

    def test_it_destroys_the_snapshot_afterwards(self) -> None:
        run = self._run()
        with volume_snapshot("zfs", "/var/lib/docker", "20260731", run=run):
            pass
        self.assertEqual(run.calls[-1], "zfs destroy tank/docker@baudolo-20260731")

    def test_it_maps_a_volume_path_through_the_dot_zfs_directory(self) -> None:
        run = self._run()
        with volume_snapshot("zfs", "/var/lib/docker", "20260731", run=run) as resolve:
            self.assertEqual(
                resolve("/var/lib/docker/volumes/postgres_data/_data"),
                "/var/lib/docker/.zfs/snapshot/baudolo-20260731/volumes/postgres_data/_data",
            )

    def test_an_unmounted_dataset_is_an_error(self) -> None:
        run = Runner({"zfs list": [""]})
        with self.assertRaises(SnapshotError):
            with volume_snapshot("zfs", "/var/lib/docker", "20260731", run=run):
                pass


class TestRejections(unittest.TestCase):
    def test_an_unknown_kind_is_rejected(self) -> None:
        run = Runner()
        with self.assertRaises(SnapshotError):
            with volume_snapshot("ext4", "/var/lib/docker", "20260731", run=run):
                pass
        self.assertEqual(run.calls, [])

    def test_a_path_outside_the_subject_is_rejected(self) -> None:
        run = Runner()
        with volume_snapshot("btrfs", "/var/lib/docker", "20260731", run=run) as resolve:
            with self.assertRaises(SnapshotError):
                resolve("/etc/passwd")

    def test_the_subject_itself_resolves_to_the_snapshot_root(self) -> None:
        run = Runner()
        with volume_snapshot("btrfs", "/var/lib/docker", "20260731", run=run) as resolve:
            self.assertEqual(resolve("/var/lib/docker"), "/var/lib/docker/.baudolo-20260731")


class Busy(Runner):
    def __call__(self, command: str) -> list[str]:
        if command.startswith("btrfs subvolume delete"):
            raise BackupException("target is busy")
        return super().__call__(command)


class TestRemovalFailure(unittest.TestCase):
    def test_a_failed_removal_does_not_fail_a_completed_run(self) -> None:
        with volume_snapshot("btrfs", "/var/lib/docker", "20260731", run=Busy()):
            pass

    def test_a_failed_removal_does_not_mask_the_body(self) -> None:
        with self.assertRaises(ZeroDivisionError):
            with volume_snapshot("btrfs", "/var/lib/docker", "20260731", run=Busy()):
                raise ZeroDivisionError


if __name__ == "__main__":
    unittest.main()
