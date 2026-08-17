"""Which volumes a snapshot of the subject actually contains.

The failure this guards against is silent: a volume with a backing store of
its own is present inside the snapshot as an empty directory, so rsync
succeeds, the generation is stamped complete, and the volume is empty in it.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from baudolo.backup.snapshot import SnapshotError, snapshot_source, unsnapshotted
from baudolo.backup.volume import Backing


class TestUnsnapshotted(unittest.TestCase):
    def setUp(self) -> None:
        self.subject = tempfile.mkdtemp()
        self.mountpoint = os.path.join(self.subject, "volumes", "app", "_data")
        os.makedirs(self.mountpoint)

    def backing(self, **kwargs) -> Backing:
        return Backing(kwargs.pop("mountpoint", self.mountpoint), **kwargs)

    def test_a_plain_local_volume_is_captured(self) -> None:
        self.assertIsNone(unsnapshotted(self.backing(), self.subject))

    def test_a_foreign_driver_is_not(self) -> None:
        reason = unsnapshotted(self.backing(driver="rexray"), self.subject)
        self.assertIn("rexray", reason)

    def test_declared_driver_options_are_not(self) -> None:
        reason = unsnapshotted(
            self.backing(options={"type": "nfs", "device": ":/exports/app"}),
            self.subject,
        )
        self.assertIn("backing store", reason)

    def test_the_declaration_decides_not_the_mount_table(self) -> None:
        """Docker unmounts an NFS volume when its last container stops."""
        with mock.patch.object(os.path, "ismount", return_value=False):
            reason = unsnapshotted(self.backing(options={"type": "nfs"}), self.subject)
        self.assertIsNotNone(reason)

    def test_a_volume_without_a_mountpoint_is_not(self) -> None:
        reason = unsnapshotted(Backing(""), self.subject)
        self.assertIn("no mountpoint", reason)

    def test_an_own_mount_is_not(self) -> None:
        with mock.patch.object(os.path, "ismount", return_value=True):
            reason = unsnapshotted(self.backing(), self.subject)
        self.assertIn("own mount", reason)

    def test_a_filesystem_boundary_is_not(self) -> None:
        real = os.stat

        def crossing(path, *args, **kwargs):
            info = real(path, *args, **kwargs)
            if os.path.realpath(path) == os.path.realpath(self.mountpoint):
                return os.stat_result(
                    (info.st_mode, info.st_ino, info.st_dev + 1, *tuple(info)[3:])
                )
            return info

        with mock.patch.object(os, "stat", side_effect=crossing):
            reason = unsnapshotted(self.backing(), self.subject)
        self.assertIn("filesystem boundary", reason)

    def test_an_unreadable_mountpoint_is_not(self) -> None:
        reason = unsnapshotted(
            self.backing(mountpoint=os.path.join(self.subject, "gone")), self.subject
        )
        self.assertIn("could not be read", reason)


class TestSnapshotSource(unittest.TestCase):
    def setUp(self) -> None:
        self.subject = tempfile.mkdtemp()
        self.mountpoint = os.path.join(self.subject, "volumes", "app", "_data")
        os.makedirs(self.mountpoint)
        self.snapshot = os.path.join(
            self.subject, ".baudolo-tag", "volumes", "app", "_data"
        )
        os.makedirs(self.snapshot)
        self.backing = Backing(self.mountpoint)

    def test_a_captured_volume_reads_from_the_snapshot(self) -> None:
        source, reason = snapshot_source(
            lambda path: self.snapshot + "/", self.backing, self.subject
        )
        self.assertEqual(source, self.snapshot + "/")
        self.assertEqual(reason, "")

    def test_an_uncaptured_volume_is_refused_before_the_resolver_runs(self) -> None:
        def resolve(path):
            raise AssertionError("must not resolve a volume the snapshot misses")

        source, reason = snapshot_source(
            resolve, Backing(self.mountpoint, options={"type": "nfs"}), self.subject
        )
        self.assertIsNone(source)
        self.assertIn("backing store", reason)

    def test_a_volume_outside_the_subject_degrades_instead_of_raising(self) -> None:
        def resolve(path):
            raise SnapshotError(f"{path} lies outside the snapshot subject")

        source, reason = snapshot_source(resolve, self.backing, self.subject)
        self.assertIsNone(source)
        self.assertIn("lies outside", reason)

    def test_a_volume_created_after_the_snapshot_degrades(self) -> None:
        source, reason = snapshot_source(
            lambda path: os.path.join(self.subject, "absent") + "/",
            self.backing,
            self.subject,
        )
        self.assertIsNone(source)
        self.assertIn("created after", reason)


if __name__ == "__main__":
    unittest.main()
