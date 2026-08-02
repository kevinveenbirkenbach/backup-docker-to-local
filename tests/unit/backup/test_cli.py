"""Contract of the backup CLI, in particular the snapshot flag pairing."""

from __future__ import annotations

import unittest
from unittest import mock

from baudolo.backup.cli import parse_args

REQUIRED = ["--compose-dir", "/compose", "--backups-dir", "/backups"]


def parse(*extra: str):
    with mock.patch("sys.argv", ["baudolo", *REQUIRED, *extra]):
        return parse_args()


class TestSnapshotFlags(unittest.TestCase):
    def test_no_snapshot_by_default(self) -> None:
        args = parse()
        self.assertIsNone(args.snapshot)
        self.assertIsNone(args.snapshot_subject)

    def test_both_flags_together_are_accepted(self) -> None:
        args = parse("--snapshot", "btrfs", "--snapshot-subject", "/var/lib/docker")
        self.assertEqual(args.snapshot, "btrfs")
        self.assertEqual(args.snapshot_subject, "/var/lib/docker")

    def test_the_kind_alone_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            parse("--snapshot", "btrfs")

    def test_the_subject_alone_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            parse("--snapshot-subject", "/var/lib/docker")

    def test_an_unsupported_kind_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            parse("--snapshot", "ext4", "--snapshot-subject", "/var/lib/docker")

    def test_zfs_is_accepted(self) -> None:
        self.assertEqual(
            parse("--snapshot", "zfs", "--snapshot-subject", "/d").snapshot, "zfs"
        )

    def test_shutdown_is_rejected_because_nothing_is_stopped(self) -> None:
        with self.assertRaises(SystemExit):
            parse("--snapshot", "btrfs", "--snapshot-subject", "/d", "--shutdown")

    def test_shutdown_stays_available_without_a_snapshot(self) -> None:
        self.assertTrue(parse("--shutdown").shutdown)

    def test_hard_restart_is_rejected_because_nothing_is_stopped(self) -> None:
        with self.assertRaises(SystemExit):
            parse(
                "--snapshot",
                "btrfs",
                "--snapshot-subject",
                "/d",
                "--hard-restart-projects",
                "mailu",
            )

    def test_hard_restart_stays_available_without_a_snapshot(self) -> None:
        self.assertEqual(
            parse("--hard-restart-projects", "mailu").hard_restart_projects, ["mailu"]
        )


class TestRequiredFlags(unittest.TestCase):
    def test_backups_dir_is_required(self) -> None:
        with mock.patch("sys.argv", ["baudolo", "--compose-dir", "/compose"]):
            with self.assertRaises(SystemExit):
                parse_args()

    def test_compose_dir_is_required(self) -> None:
        with mock.patch("sys.argv", ["baudolo", "--backups-dir", "/backups"]):
            with self.assertRaises(SystemExit):
                parse_args()


if __name__ == "__main__":
    unittest.main()
