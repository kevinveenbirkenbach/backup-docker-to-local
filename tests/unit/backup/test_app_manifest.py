"""What main() records in the manifest for each volume it touched."""

from __future__ import annotations

import unittest
from unittest import mock

from baudolo.backup import app
from baudolo.backup.dumps import VolumeOutcome
from baudolo.backup.volume import Backing

from . import REQUIRED_PAIRS

ARGV = ["baudolo", *[arg for pair in REQUIRED_PAIRS for arg in pair]]


def drive(argv: list[str], dump_result: VolumeOutcome) -> dict:
    """Run main() over one volume and return the manifest's volume section.

    Args:
        argv: the command line under test.
        dump_result: what backup_dumps_for_volume reports.
    """
    with (
        mock.patch("sys.argv", argv),
        mock.patch.object(app, "get_machine_id", return_value="machine"),
        mock.patch.object(app, "create_version_directory", return_value="/gen"),
        mock.patch.object(app, "create_volume_directory", return_value="/gen/vol"),
        mock.patch.object(app, "load_databases_df", return_value=None),
        mock.patch.object(app, "docker_volume_names", return_value=["pgdata"]),
        mock.patch.object(app, "containers_using_volume", return_value=["db"]),
        mock.patch.object(app, "volume_is_fully_ignored", return_value=False),
        mock.patch.object(app, "backup_dumps_for_volume", return_value=dump_result),
        mock.patch.object(app, "inspect_backing", return_value=Backing("/data")),
        mock.patch.object(app, "write_manifest") as manifest,
        mock.patch.object(app, "stamp_directory"),
        mock.patch.object(app, "handle_docker_compose_services"),
        mock.patch("os.path.isdir", return_value=True),
        mock.patch.object(app, "backup_volume"),
        mock.patch.object(app, "filter_stoppable", return_value=[]),
        mock.patch.object(app, "requires_stop", return_value=False),
        mock.patch.object(app, "change_containers_status"),
    ):
        app.main()
    return manifest.call_args.args[1]


class TestManifest(unittest.TestCase):
    def test_a_database_volume_without_a_dump_is_recorded_as_undumped(self) -> None:
        volumes = drive(
            [*ARGV, "--only-sql"],
            VolumeOutcome(database=True, dumped=False, engine="postgres"),
        )
        self.assertEqual(
            volumes["pgdata"],
            VolumeOutcome(database=True, dumped=False, engine="postgres"),
        )

    def test_a_dumped_database_volume_is_recorded_as_dumped(self) -> None:
        volumes = drive(
            [*ARGV, "--only-sql"],
            VolumeOutcome(database=True, dumped=True, engine="mariadb"),
        )
        self.assertEqual(volumes["pgdata"].dumped, True)
        self.assertEqual(volumes["pgdata"].engine, "mariadb")

    def test_a_plain_volume_is_recorded_as_no_database(self) -> None:
        volumes = drive(ARGV, VolumeOutcome(database=False, dumped=False))
        self.assertEqual(volumes["pgdata"].database, False)
        self.assertIsNone(volumes["pgdata"].engine)

    def test_the_dumped_volume_is_recorded_even_though_the_copy_is_skipped(
        self,
    ) -> None:
        """--only-sql returns to the loop head on success, before the copy."""
        volumes = drive(
            [*ARGV, "--only-sql"],
            VolumeOutcome(database=True, dumped=True, engine="postgres"),
        )
        self.assertIn("pgdata", volumes)


if __name__ == "__main__":
    unittest.main()
