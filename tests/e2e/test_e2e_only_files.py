"""--only-files backs a database up as a file tree and asks for no credentials.

The run deliberately passes no --databases-csv at all: a host that only copies
files has no reason to hold database passwords, and requiring the file would
make the flag useless there.
"""

import unittest

from .helpers import (
    POSTGRES_DATA_DIR,
    POSTGRES_IMAGE,
    backup_path,
    cleanup_docker,
    create_minimal_compose_dir,
    ensure_empty_dir,
    latest_version_dir,
    require_docker,
    run,
    unique,
    wait_for_postgres,
)

MARKER = "only-files-marker"


class TestE2EOnlyFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-only-files")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)
        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        cls.pg_container = f"{cls.prefix}-pg"
        cls.pg_volume = f"{cls.prefix}-pg-vol"
        cls.containers = [cls.pg_container]
        cls.volumes = [cls.pg_volume]

        run(["docker", "volume", "create", cls.pg_volume])
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cls.pg_container,
                "-e",
                "POSTGRES_PASSWORD=pgpw",
                "-e",
                "POSTGRES_DB=appdb",
                "-e",
                "POSTGRES_USER=postgres",
                "-v",
                f"{cls.pg_volume}:{POSTGRES_DATA_DIR}",
                POSTGRES_IMAGE,
            ]
        )
        wait_for_postgres(cls.pg_container, user="postgres", timeout_s=90)
        run(
            [
                "docker",
                "exec",
                cls.pg_container,
                "sh",
                "-lc",
                f"echo '{MARKER}' > {POSTGRES_DATA_DIR}/marker.txt",
            ]
        )

        cp = run(
            [
                "baudolo",
                "--compose-dir",
                cls.compose_dir,
                "--repo-name",
                cls.repo_name,
                "--backups-dir",
                cls.backups_dir,
                "--images-no-stop-required",
                POSTGRES_IMAGE,
                "--only-files",
            ],
            capture=True,
            check=True,
        )
        cls.stdout = cp.stdout or ""
        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    def _volume_dir(self):
        return backup_path(
            self.backups_dir, self.repo_name, self.version, self.pg_volume
        )

    def test_the_database_volume_is_backed_up_as_files(self) -> None:
        marker = self._volume_dir() / "files" / "marker.txt"
        self.assertTrue(marker.is_file(), f"expected a file backup at {marker}")
        self.assertEqual(marker.read_text(encoding="utf-8").strip(), MARKER)

    def test_no_dump_is_written(self) -> None:
        sql_dir = self._volume_dir() / "sql"
        dumps = list(sql_dir.glob("*.sql")) if sql_dir.exists() else []
        self.assertEqual(dumps, [], f"did not expect any dump, found: {dumps}")

    def test_the_missing_databases_csv_is_not_reported(self) -> None:
        self.assertNotIn("databases.csv", self.stdout)


if __name__ == "__main__":
    unittest.main()
