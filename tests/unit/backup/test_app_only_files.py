"""Contract of --only-files: no dump is attempted, every volume is copied."""

from __future__ import annotations

import unittest
from unittest import mock

from baudolo.backup import app
from baudolo.backup.volume import Backing

from . import REQUIRED_PAIRS

ARGV_WITHOUT_CSV = [
    "baudolo",
    *[arg for pair in REQUIRED_PAIRS if pair[0] != "--databases-csv" for arg in pair],
    "--only-files",
]


def drive(argv: list[str]) -> tuple[list[str], list, list]:
    backed_up: list[str] = []

    def record_backup(versions_dir, volume_name, volume_dir, *, authoritative, source):
        backed_up.append(volume_name)

    with (
        mock.patch("sys.argv", argv),
        mock.patch.object(app, "get_machine_id", return_value="machine"),
        mock.patch.object(app, "create_version_directory", return_value="/gen"),
        mock.patch.object(app, "create_volume_directory", return_value="/gen/vol"),
        mock.patch.object(app, "load_databases_df") as load_csv,
        mock.patch.object(app, "docker_volume_names", return_value=["pgdata"]),
        mock.patch.object(app, "containers_using_volume", return_value=["db"]),
        mock.patch.object(app, "volume_is_fully_ignored", return_value=False),
        mock.patch.object(app, "backup_dumps_for_volume") as dumps,
        mock.patch.object(app, "inspect_backing", return_value=Backing("/data")),
        mock.patch.object(app, "stamp_directory"),
        mock.patch.object(app, "handle_docker_compose_services"),
        mock.patch.object(app.os.path, "isdir", return_value=True),
        mock.patch.object(app, "backup_volume", side_effect=record_backup),
        mock.patch.object(app, "filter_stoppable", return_value=[]),
        mock.patch.object(app, "requires_stop", return_value=False),
        mock.patch.object(app, "change_containers_status"),
    ):
        app.main()
    return backed_up, dumps.mock_calls, load_csv.mock_calls


class TestOnlyFiles(unittest.TestCase):
    def test_no_dump_is_attempted(self) -> None:
        _backed_up, dumps, _load_csv = drive(ARGV_WITHOUT_CSV)
        self.assertEqual(dumps, [])

    def test_the_databases_csv_is_never_read(self) -> None:
        """It may legitimately be absent, so reading it would abort the run."""
        _backed_up, _dumps, load_csv = drive(ARGV_WITHOUT_CSV)
        self.assertEqual(load_csv, [])

    def test_the_volume_is_still_copied(self) -> None:
        backed_up, _dumps, _load_csv = drive(ARGV_WITHOUT_CSV)
        self.assertEqual(backed_up, ["pgdata"])


if __name__ == "__main__":
    unittest.main()
