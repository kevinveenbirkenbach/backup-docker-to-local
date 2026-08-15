import unittest

from .helpers import (
    POSTGRES_IMAGE,
    POSTGRES_DATA_DIR,
    backup_run,
    backup_path,
    cleanup_docker,
    create_minimal_compose_dir,
    ensure_empty_dir,
    latest_version_dir,
    require_docker,
    unique,
    write_databases_csv,
    run,
    wait_for_postgres,
)

REGISTRY_HOST = "svc-db-mariadb-swarm-mgr-01:5000"


class TestE2EEngineDetectionRegistryPrefix(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-registry-prefix")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)
        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        cls.image = f"{REGISTRY_HOST}/postgres_custom:17-3.5"
        cls.pg_container = f"{cls.prefix}-pg"
        cls.pg_volume = f"{cls.prefix}-pg-vol"
        cls.containers = [cls.pg_container]
        cls.volumes = [cls.pg_volume]

        run(["docker", "pull", POSTGRES_IMAGE])
        run(["docker", "tag", POSTGRES_IMAGE, cls.image])
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
                cls.image,
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
                "psql -U postgres -d appdb -c \"CREATE TABLE t (id int primary key, v text); INSERT INTO t VALUES (1,'ok');\"",
            ]
        )

        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(
            cls.databases_csv, [(cls.pg_container, "appdb", "postgres", "pgpw")]
        )

        backup_run(
            backups_dir=cls.backups_dir,
            repo_name=cls.repo_name,
            compose_dir=cls.compose_dir,
            databases_csv=cls.databases_csv,
            database_containers=[cls.pg_container],
            images_no_stop_required=[cls.image],
        )

        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)
        run(["docker", "rmi", cls.image], check=False)

    def test_the_registry_host_does_not_pick_the_engine(self) -> None:
        p = (
            backup_path(self.backups_dir, self.repo_name, self.version, self.pg_volume)
            / "sql"
            / "appdb.backup.sql"
        )
        self.assertTrue(p.is_file(), f"Expected a pg_dump at: {p}")
        self.assertIn("Dumped by pg_dump", p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
