"""Contract of app.main's live copy when no snapshot is taken."""

from __future__ import annotations

import unittest
from unittest import mock

from baudolo.backup import app
from baudolo.backup.shell import BackupError
from baudolo.backup.volume import Backing

from . import BASE_ARGV


def drive(*, stop: bool, fail_live: bool) -> list[str]:
    events: list[str] = []

    def record(versions_dir, volume_name, volume_dir, *, authoritative, source):
        events.append("authoritative" if authoritative else "live")
        if fail_live and not authoritative:
            raise BackupError("rsync exit code 23")

    with (
        mock.patch("sys.argv", BASE_ARGV),
        mock.patch.object(app, "get_machine_id", return_value="machine"),
        mock.patch.object(app, "create_version_directory", return_value="/gen"),
        mock.patch.object(app, "create_volume_directory", return_value="/gen/vol"),
        mock.patch.object(app, "load_databases_df", return_value=None),
        mock.patch.object(app, "docker_volume_names", return_value=["vol"]),
        mock.patch.object(app, "containers_using_volume", return_value=["c"]),
        mock.patch.object(app, "volume_is_fully_ignored", return_value=False),
        mock.patch.object(app, "backup_dumps_for_volume", return_value=(False, False)),
        mock.patch.object(
            app,
            "inspect_backing",
            return_value=Backing("/var/lib/docker/volumes/vol/_data"),
        ),
        mock.patch.object(app, "requires_stop", return_value=stop),
        mock.patch.object(app, "filter_stoppable", return_value=["c"]),
        mock.patch.object(
            app,
            "change_containers_status",
            side_effect=lambda containers, status: events.append(status),
        ),
        mock.patch.object(app, "write_manifest"),
        mock.patch.object(app, "stamp_directory"),
        mock.patch.object(app, "handle_docker_compose_services"),
        mock.patch.object(app, "backup_volume", side_effect=record),
    ):
        app.main()
    return events


class TestLivePreCopy(unittest.TestCase):
    def test_a_failed_pre_copy_is_replaced_by_the_stopped_copy(self) -> None:
        self.assertEqual(
            drive(stop=True, fail_live=True),
            ["live", "stop", "authoritative", "start"],
        )

    def test_a_failed_live_copy_without_a_stop_aborts_the_run(self) -> None:
        with self.assertRaises(BackupError):
            drive(stop=False, fail_live=True)

    def test_a_volume_without_a_stop_is_copied_live_once(self) -> None:
        self.assertEqual(drive(stop=False, fail_live=False), ["live"])


if __name__ == "__main__":
    unittest.main()
