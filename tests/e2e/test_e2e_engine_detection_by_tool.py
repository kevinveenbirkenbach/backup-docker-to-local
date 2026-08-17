"""The engine comes from the tools a container ships, not from its image name.

Two containers in one backup run, each lying in one direction:

* a real Postgres tagged `<prefix>-database`, the way a dedicated database is
  built inside an app's own stack - no engine token anywhere in the name;
* an Alpine tagged `postgres:<prefix>`, carrying the token without shipping a
  single Postgres binary.

Reading the name gets both wrong, and the second one fatally: pg_dump exits 127
inside Alpine and takes the whole run with it.
"""

import unittest

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

IMPOSTOR_BASE_IMAGE = "alpine:3.20"
MARKER = "engine-detection-by-tool"


class TestE2EEngineDetectionByTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-engine-by-tool")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)
        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        cls.engine_image = f"{cls.prefix}-database:17"
        cls.impostor_image = f"postgres:{cls.prefix}"

        cls.engine_container = f"{cls.prefix}-engine"
        cls.impostor_container = f"{cls.prefix}-impostor"
        cls.engine_volume = f"{cls.prefix}-engine-vol"
        cls.impostor_volume = f"{cls.prefix}-impostor-vol"

        cls.containers = [cls.engine_container, cls.impostor_container]
        cls.volumes = [cls.engine_volume, cls.impostor_volume]

        run(["docker", "pull", POSTGRES_IMAGE])
        run(["docker", "pull", IMPOSTOR_BASE_IMAGE])
        run(["docker", "tag", POSTGRES_IMAGE, cls.engine_image])
        run(["docker", "tag", IMPOSTOR_BASE_IMAGE, cls.impostor_image])
        run(["docker", "volume", "create", cls.engine_volume])
        run(["docker", "volume", "create", cls.impostor_volume])

        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cls.engine_container,
                "-e",
                "POSTGRES_PASSWORD=pgpw",
                "-e",
                "POSTGRES_DB=appdb",
                "-e",
                "POSTGRES_USER=postgres",
                "-v",
                f"{cls.engine_volume}:{POSTGRES_DATA_DIR}",
                cls.engine_image,
            ]
        )
        wait_for_postgres(cls.engine_container, user="postgres", timeout_s=90)
        run(
            [
                "docker",
                "exec",
                cls.engine_container,
                "sh",
                "-lc",
                (
                    "psql -U postgres -d appdb -c "
                    '"CREATE TABLE t (id int primary key, v text); '
                    "INSERT INTO t VALUES (1,'ok');\""
                ),
            ]
        )

        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cls.impostor_container,
                "-v",
                f"{cls.impostor_volume}:/data",
                cls.impostor_image,
                "sh",
                "-lc",
                f"echo '{MARKER}' > /data/marker.txt && sleep 3600",
            ]
        )

        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(
            cls.databases_csv,
            [
                (cls.engine_container, "appdb", "postgres", "pgpw"),
                (cls.impostor_container, "appdb", "postgres", "pgpw"),
            ],
        )

        backup_run(
            backups_dir=cls.backups_dir,
            repo_name=cls.repo_name,
            compose_dir=cls.compose_dir,
            databases_csv=cls.databases_csv,
            database_containers=[cls.engine_container, cls.impostor_container],
            images_no_stop_required=[cls.engine_image, cls.impostor_image],
            only_sql=True,
        )

        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)
        run(["docker", "rmi", cls.engine_image], check=False)
        run(["docker", "rmi", cls.impostor_image], check=False)

    def _volume_dir(self, volume: str):
        return backup_path(self.backups_dir, self.repo_name, self.version, volume)

    def test_an_engine_without_an_engine_name_is_still_dumped(self) -> None:
        dump = self._volume_dir(self.engine_volume) / "sql" / "appdb.backup.sql"
        self.assertTrue(
            dump.is_file(),
            f"a Postgres tagged '{self.engine_image}' produced no dump at {dump}",
        )
        self.assertIn("Dumped by pg_dump", dump.read_text(encoding="utf-8"))

    def test_an_engine_name_without_an_engine_is_not_dumped(self) -> None:
        sql_dir = self._volume_dir(self.impostor_volume) / "sql"
        dumps = list(sql_dir.glob("*.sql")) if sql_dir.exists() else []
        self.assertEqual(
            dumps,
            [],
            f"'{self.impostor_image}' ships no Postgres yet was dumped: {dumps}",
        )

    def test_the_recognised_engine_is_dumped_instead_of_copied(self) -> None:
        files = self._volume_dir(self.engine_volume) / "files"
        self.assertFalse(
            files.exists(),
            f"--only-sql still copied the engine's files to {files}",
        )

    def test_the_impostor_falls_through_to_a_file_backup(self) -> None:
        files = self._volume_dir(self.impostor_volume) / "files"
        self.assertTrue(files.is_dir(), f"expected a file backup at {files}")
        self.assertEqual(
            (files / "marker.txt").read_text(encoding="utf-8").strip(), MARKER
        )


if __name__ == "__main__":
    unittest.main()
