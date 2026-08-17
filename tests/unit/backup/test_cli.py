"""Contract of the backup CLI, in particular the snapshot flag pairing."""

from __future__ import annotations

import unittest
from unittest import mock

from baudolo.backup.cli import parse_args

from . import REQUIRED, REQUIRED_PAIRS


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
    def test_no_flag_falls_back_to_a_default(self) -> None:
        for omitted, _ in REQUIRED_PAIRS:
            argv = [a for pair in REQUIRED_PAIRS if pair[0] != omitted for a in pair]
            with (
                self.subTest(omitted=omitted),
                mock.patch("sys.argv", ["baudolo", *argv]),
                self.assertRaises(SystemExit),
            ):
                parse_args()


class TestBackupScope(unittest.TestCase):
    """--only-sql and --only-files name the two halves a generation can hold."""

    def test_both_halves_by_default(self) -> None:
        args = parse()
        self.assertFalse(args.only_sql)
        self.assertFalse(args.only_files)

    def test_either_half_alone_is_accepted(self) -> None:
        self.assertTrue(parse("--only-sql").only_sql)
        self.assertTrue(parse("--only-files").only_files)

    def test_asking_for_both_halves_alone_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            parse("--only-sql", "--only-files")

    def test_only_files_needs_no_databases_csv(self) -> None:
        argv = [
            arg
            for pair in REQUIRED_PAIRS
            if pair[0] != "--databases-csv"
            for arg in pair
        ]
        with mock.patch("sys.argv", ["baudolo", *argv, "--only-files"]):
            self.assertIsNone(parse_args().databases_csv)


if __name__ == "__main__":
    unittest.main()
