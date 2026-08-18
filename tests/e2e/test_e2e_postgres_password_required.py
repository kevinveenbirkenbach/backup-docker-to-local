"""An engine whose loopback auth really demands a password.

Every other Postgres scenario runs stock postgres:alpine, whose generated
pg_hba grants trust on 127.0.0.1 and ::1 - so `pg_dump -h localhost` never
needs the password and a dump succeeds whether or not baudolo hands one to the
container. This module makes the password mandatory, which is what a dedicated
engine on a real host does.
"""

import unittest
from pathlib import Path

from baudolo.generation import CLUSTER_SUFFIX, DUMP_SUFFIX, FILES_DIR, SQL_DIR

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


class TestE2EPostgresPasswordRequired(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-pg-password-required")
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
                # The entrypoint evals this into its initdb call, so the host
                # lines of pg_hba demand scram while the local socket stays
                # trust - the entrypoint's own init and the seeding below keep
                # working, and only a TCP connection needs the password.
                "-e",
                "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256",
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
                (
                    'psql -U postgres -d appdb -c "CREATE TABLE t (id int primary '
                    "key, v text); INSERT INTO t VALUES (1,'ok');\""
                ),
            ],
            check=True,
        )

        cls.unauthenticated = run(
            [
                "docker",
                "exec",
                cls.pg_container,
                "sh",
                "-lc",
                "pg_dump -U postgres -d appdb -h localhost",
            ],
            capture=True,
            check=False,
        )

        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(
            cls.databases_csv,
            [
                (cls.pg_container, "appdb", "postgres", "pgpw"),
                (cls.pg_container, "*", "postgres", "pgpw"),
            ],
        )

        backup_run(
            backups_dir=cls.backups_dir,
            repo_name=cls.repo_name,
            compose_dir=cls.compose_dir,
            databases_csv=cls.databases_csv,
            database_containers=[cls.pg_container],
            images_no_stop_required=[POSTGRES_IMAGE],
            only_sql=True,
        )
        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    def volume_dir(self) -> Path:
        return backup_path(
            self.backups_dir, self.repo_name, self.version, self.pg_volume
        )

    def test_a_dump_without_the_password_is_refused_by_the_server(self) -> None:
        """Without this the module is vacuous: a pg_hba still saying trust would
        let a baudolo that forwards nothing pass just as well."""
        self.assertNotEqual(self.unauthenticated.returncode, 0)
        self.assertIn("no password supplied", self.unauthenticated.stderr or "")

    def test_the_configured_database_was_dumped(self) -> None:
        dump = self.volume_dir() / SQL_DIR / f"appdb{DUMP_SUFFIX}"
        self.assertTrue(dump.is_file(), f"expected a dump at {dump}")
        self.assertIn("Dumped by pg_dump", dump.read_text(encoding="utf-8"))

    def test_the_dump_carries_the_payload(self) -> None:
        """pg_dump emits table data as COPY ... FROM stdin, so the row reads as
        tab-separated values rather than as an INSERT literal."""
        dump = self.volume_dir() / SQL_DIR / f"appdb{DUMP_SUFFIX}"
        self.assertIn("COPY public.t (id, v) FROM stdin;", dump.read_text("utf-8"))
        self.assertIn("1\tok", dump.read_text(encoding="utf-8"))

    def test_the_cluster_row_was_dumped_too(self) -> None:
        cluster = self.volume_dir() / SQL_DIR / f"{self.pg_container}{CLUSTER_SUFFIX}"
        self.assertTrue(cluster.is_file(), f"expected a cluster dump at {cluster}")
        self.assertIn("CREATE DATABASE", cluster.read_text(encoding="utf-8"))

    def test_only_sql_left_no_file_copy_behind(self) -> None:
        self.assertFalse((self.volume_dir() / FILES_DIR).exists())


if __name__ == "__main__":
    unittest.main()
