"""Contract of --volumes-no-backup-required: exclusion is per volume name,
independent of which containers use it."""

from __future__ import annotations

import unittest
from unittest import mock

from baudolo.backup import app

ARGV = [
    "baudolo",
    "--compose-dir",
    "/compose",
    "--backups-dir",
    "/backups",
    "--volumes-no-backup-required",
    "derived",
]


def drive() -> tuple[list[str], list[str], list[str]]:
    backed_up: list[str] = []
    created: list[str] = []
    inspected: list[str] = []

    def record_backup(versions_dir, volume_name, volume_dir, *, authoritative, source):
        backed_up.append(volume_name)

    with (
        mock.patch("sys.argv", ARGV),
        mock.patch.object(app, "get_machine_id", return_value="machine"),
        mock.patch.object(app, "create_version_directory", return_value="/gen"),
        mock.patch.object(
            app,
            "create_volume_directory",
            side_effect=lambda _version_dir, name: created.append(name) or "/gen/vol",
        ),
        mock.patch.object(app, "load_databases_df", return_value=None),
        mock.patch.object(
            app, "docker_volume_names", return_value=["derived", "state"]
        ),
        mock.patch.object(
            app,
            "containers_using_volume",
            side_effect=lambda name: inspected.append(name) or ["app"],
        ),
        mock.patch.object(app, "volume_is_fully_ignored", return_value=False),
        mock.patch.object(app, "backup_dumps_for_volume", return_value=(False, False)),
        mock.patch.object(app, "get_storage_path", return_value="/data/"),
        mock.patch.object(app, "stamp_directory"),
        mock.patch.object(app, "handle_docker_compose_services"),
        mock.patch.object(app.os.path, "isdir", return_value=True),
        mock.patch.object(app, "backup_volume", side_effect=record_backup),
        mock.patch.object(app, "filter_stoppable", return_value=[]),
        mock.patch.object(app, "requires_stop", return_value=False),
        mock.patch.object(app, "change_containers_status"),
    ):
        app.main()
    return backed_up, created, inspected


class TestVolumesNoBackupRequired(unittest.TestCase):
    def test_the_named_volume_is_never_backed_up(self) -> None:
        backed_up, _created, _inspected = drive()
        self.assertNotIn("derived", backed_up)

    def test_a_sibling_volume_of_the_same_container_survives(self) -> None:
        backed_up, _created, _inspected = drive()
        self.assertEqual(backed_up, ["state"])

    def test_no_generation_directory_is_created_for_it(self) -> None:
        _backed_up, created, _inspected = drive()
        self.assertEqual(created, ["state"])

    def test_the_skip_precedes_the_container_inspection(self) -> None:
        _backed_up, _created, inspected = drive()
        self.assertEqual(inspected, ["state"])


if __name__ == "__main__":
    unittest.main()
