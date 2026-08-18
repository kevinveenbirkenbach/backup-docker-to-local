"""An application container that ships the engine's client tools.

This is the shape a dedicated database deploys in: the engine runs as
`<app>-database` while the application itself runs as `<app>`, and neither is
declared through --database-containers, so both names go through the instance
regex. `<app>-database` loses its suffix and lands on the instance `<app>` -
and `<app>` carries no database token at all, so a fallback that returns the
name unchanged lands on that same instance and offers the application container
as a second engine for the same row.

Discourse is the live example: its application container is named `discourse`
by its own launcher and ships pg_dumpall, so a dump command starts there and
writes a file that looks like a backup and holds none of the data.
"""

import unittest
from pathlib import Path

from baudolo.generation import DUMP_SUFFIX, FILES_DIR, SQL_DIR

from .helpers import (
    POSTGRES_DATA_DIR,
    POSTGRES_IMAGE,
    backup_path,
    backup_run,
    cleanup_docker,
    create_minimal_compose_dir,
    ensure_empty_dir,
    latest_version_dir,
    require_docker,
    run,
    unique,
    wait_for_postgres,
    write_databases_csv,
)

MARKER = "the-application-volume-holds-files"
PAYLOAD = "shop-payload"


class TestE2EAppContainerShipsClientTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        # uuid4 hex may begin with "db", which the instance regex would split
        # on and turn the application container into a different instance,
        # hiding exactly the collision this module is about.
        cls.prefix = unique("baudolo-e2e-app-tools").replace("-db", "-xb")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)
        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        cls.engine = f"{cls.prefix}-shop-database"
        cls.app = f"{cls.prefix}-shop"
        cls.engine_volume = f"{cls.prefix}-shop-database-vol"
        cls.app_volume = f"{cls.prefix}-shop-app-vol"
        cls.containers = [cls.engine, cls.app]
        cls.volumes = [cls.engine_volume, cls.app_volume]

        run(["docker", "volume", "create", cls.engine_volume])
        run(["docker", "volume", "create", cls.app_volume])

        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cls.engine,
                "-e",
                "POSTGRES_PASSWORD=shoppw",
                "-e",
                "POSTGRES_DB=shopdb",
                "-e",
                "POSTGRES_USER=postgres",
                "-v",
                f"{cls.engine_volume}:{POSTGRES_DATA_DIR}",
                POSTGRES_IMAGE,
            ]
        )

        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cls.app,
                "--entrypoint",
                "sh",
                "-v",
                f"{cls.app_volume}:/data",
                POSTGRES_IMAGE,
                "-c",
                f"echo '{MARKER}' > /data/marker.txt && sleep 3600",
            ]
        )

        wait_for_postgres(cls.engine, user="postgres", timeout_s=90)
        run(
            [
                "docker",
                "exec",
                cls.engine,
                "sh",
                "-lc",
                (
                    'psql -U postgres -d shopdb -c "CREATE TABLE orders (id int, '
                    f"note text); INSERT INTO orders VALUES (1,'{PAYLOAD}');\""
                ),
            ],
            check=True,
        )

        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(
            cls.databases_csv,
            [(cls.app, "shopdb", "postgres", "shoppw")],
        )

        backup_run(
            backups_dir=cls.backups_dir,
            repo_name=cls.repo_name,
            compose_dir=cls.compose_dir,
            databases_csv=cls.databases_csv,
            database_containers=["dummy-db"],
            images_no_stop_required=[POSTGRES_IMAGE],
        )
        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    def volume_dir(self, volume: str) -> Path:
        return backup_path(self.backups_dir, self.repo_name, self.version, volume)

    def test_the_engine_volume_was_dumped(self) -> None:
        dump = self.volume_dir(self.engine_volume) / SQL_DIR / f"shopdb{DUMP_SUFFIX}"
        self.assertTrue(dump.is_file(), f"expected a dump at {dump}")
        self.assertIn(PAYLOAD, dump.read_text(encoding="utf-8"))

    def test_the_application_volume_produced_no_dump(self) -> None:
        """The collision this module exists for: the application container
        answers the same instance as the engine and starts a dump of its own."""
        sql_dir = self.volume_dir(self.app_volume) / SQL_DIR
        self.assertFalse(
            sql_dir.exists(),
            f"the application container was dumped: {sorted(sql_dir.iterdir())}"
            if sql_dir.exists()
            else "",
        )

    def test_the_application_volume_was_backed_up_as_files(self) -> None:
        """Refusing the dump must not cost the volume its backup."""
        marker = self.volume_dir(self.app_volume) / FILES_DIR / "marker.txt"
        self.assertTrue(marker.is_file(), f"expected a file backup at {marker}")
        self.assertIn(MARKER, marker.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
