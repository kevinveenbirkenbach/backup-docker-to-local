"""Contract of app.main's snapshot branch - the caller that runs in production."""

from __future__ import annotations

import unittest
from unittest import mock

from baudolo.backup import app
from baudolo.backup import snapshot as snapshot_mod
from baudolo.backup.snapshot import volume_snapshot
from baudolo.backup.volume import Backing

from . import BASE_ARGV


def stubbed_snapshot(kind: str, subject: str, tag: str):
    return volume_snapshot(kind, subject, tag, run=lambda command: [])


ARGV = [
    *BASE_ARGV,
    "--snapshot",
    "btrfs",
    "--snapshot-subject",
    "/var/lib/docker",
]


def drive(*, present: bool = True, reason: str | None = None) -> list[dict]:
    calls: list[dict] = []

    def record(versions_dir, volume_name, volume_dir, *, authoritative, source):
        calls.append(
            {"volume": volume_name, "authoritative": authoritative, "source": source}
        )

    with (
        mock.patch("sys.argv", ARGV),
        mock.patch.object(app, "get_machine_id", return_value="machine"),
        mock.patch.object(app, "create_version_directory", return_value="/gen"),
        mock.patch.object(app, "create_volume_directory", return_value="/gen/vol"),
        mock.patch.object(app, "load_databases_df", return_value=None),
        mock.patch.object(app, "docker_volume_names", return_value=["vol"]),
        mock.patch.object(app, "containers_using_volume", return_value=[]),
        mock.patch.object(app, "volume_is_fully_ignored", return_value=False),
        mock.patch.object(app, "backup_dumps_for_volume", return_value=(False, False)),
        mock.patch.object(
            app,
            "inspect_backing",
            return_value=Backing("/var/lib/docker/volumes/vol/_data"),
        ),
        mock.patch.object(snapshot_mod, "unsnapshotted", return_value=reason),
        mock.patch.object(app, "stamp_directory"),
        mock.patch.object(app, "handle_docker_compose_services"),
        mock.patch.object(app.os.path, "isdir", return_value=present),
        mock.patch.object(app, "backup_volume", side_effect=record),
        mock.patch.object(app, "volume_snapshot", stubbed_snapshot),
    ):
        app.main()
    return calls


class TestSnapshotBranch(unittest.TestCase):
    def test_it_passes_a_path_ending_in_a_separator(self) -> None:
        source = drive(present=True)[0]["source"]
        self.assertTrue(source.endswith("/volumes/vol/_data/"), source)
        self.assertNotIn("/var/lib/docker/volumes", source)

    def test_it_reads_from_the_snapshot_and_not_from_the_live_tree(self) -> None:
        source = drive(present=True)[0]["source"]
        self.assertTrue(source.startswith("/var/lib/docker/.baudolo-"), source)

    def test_it_compares_by_content_against_the_previous_generation(self) -> None:
        self.assertTrue(drive(present=True)[0]["authoritative"])

    def test_a_volume_missing_from_the_snapshot_is_copied_live(self) -> None:
        call = drive(present=False)[0]
        self.assertEqual(call["source"], "/var/lib/docker/volumes/vol/_data/")
        self.assertFalse(call["authoritative"])

    def test_a_volume_with_its_own_backing_store_is_copied_live(self) -> None:
        call = drive(reason="it declares its own backing store")[0]
        self.assertEqual(call["source"], "/var/lib/docker/volumes/vol/_data/")
        self.assertFalse(
            call["authoritative"],
            "the snapshot holds an empty directory for it, not its data",
        )


if __name__ == "__main__":
    unittest.main()
