# tests/e2e/test_e2e_postgres_full.py
import unittest

from .helpers import (
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


class TestE2EPostgresFull(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-postgres-full")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)
        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        cls.pg_container = f"{cls.prefix}-pg"
        cls.pg_volume = f"{cls.prefix}-pg-vol"
        cls.containers = [cls.pg_container]
        cls.volumes = [cls.pg_volume]

        run(["docker", "volume", "create", cls.pg_volume])

        run([
            "docker", "run", "-d",
            "--name", cls.pg_container,
            "-e", "POSTGRES_PASSWORD=pgpw",
            "-e", "POSTGRES_DB=appdb",
            "-e", "POSTGRES_USER=postgres",
            "-v", f"{cls.pg_volume}:/var/lib/postgresql/data",
            "postgres:16",
        ])
        wait_for_postgres(cls.pg_container, user="postgres", timeout_s=90)

        # Create a table + data
        run([
            "docker", "exec", cls.pg_container,
            "sh", "-lc",
            "psql -U postgres -d appdb -c \"CREATE TABLE t (id int primary key, v text); INSERT INTO t VALUES (1,'ok');\"",
        ])

        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(cls.databases_csv, [(cls.pg_container, "appdb", "postgres", "pgpw")])

        backup_run(
            backups_dir=cls.backups_dir,
            repo_name=cls.repo_name,
            compose_dir=cls.compose_dir,
            databases_csv=cls.databases_csv,
            database_containers=[cls.pg_container],
            images_no_stop_required=["postgres", "mariadb", "mysql", "alpine"],
        )

        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

        # Wipe schema
        run([
            "docker", "exec", cls.pg_container,
            "sh", "-lc",
            "psql -U postgres -d appdb -c \"DROP TABLE t;\"",
        ])

        # Restore
        run([
            "baudolo-restore", "postgres",
            cls.pg_volume, cls.hash, cls.version,
            "--backups-dir", cls.backups_dir,
            "--repo-name", cls.repo_name,
            "--container", cls.pg_container,
            "--db-name", "appdb",
            "--db-user", "postgres",
            "--db-password", "pgpw",
            "--empty",
        ])

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    def test_dump_file_exists(self) -> None:
        p = backup_path(self.backups_dir, self.repo_name, self.version, self.pg_volume) / "sql" / "appdb.backup.sql"
        self.assertTrue(p.is_file(), f"Expected dump file at: {p}")

    def test_data_restored(self) -> None:
        p = run([
            "docker", "exec", self.pg_container,
            "sh", "-lc",
            "psql -U postgres -d appdb -t -c \"SELECT v FROM t WHERE id=1;\"",
        ])
        self.assertEqual((p.stdout or "").strip(), "ok")
