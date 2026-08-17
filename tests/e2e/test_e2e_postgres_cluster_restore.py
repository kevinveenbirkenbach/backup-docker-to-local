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

# One statement per entry: psql wraps a multi-statement -c in a transaction,
# and CREATE DATABASE is forbidden inside one.
SEED_SQL = (
    "CREATE ROLE app LOGIN PASSWORD 'apppw'",
    "CREATE DATABASE first OWNER app",
    "CREATE DATABASE second OWNER app",
)
DROP_SQL = (
    "DROP DATABASE first",
    "DROP DATABASE second",
    "DROP ROLE app",
)
FIRST_SQL = "CREATE TABLE t (v text); INSERT INTO t VALUES ('first-payload');"
SECOND_SQL = "CREATE TABLE t (v text); INSERT INTO t VALUES ('second-payload');"


class TestE2EPostgresClusterRestore(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-pg-cluster")
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
                "-v",
                f"{cls.pg_volume}:{POSTGRES_DATA_DIR}",
                POSTGRES_IMAGE,
            ]
        )
        wait_for_postgres(cls.pg_container, user="postgres")

        for statement in SEED_SQL:
            cls._psql("postgres", statement)
        cls._psql("first", FIRST_SQL)
        cls._psql("second", SECOND_SQL)

        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(
            cls.databases_csv, [(cls.pg_container, "*", "postgres", "pgpw")]
        )

        backup_run(
            backups_dir=cls.backups_dir,
            repo_name=cls.repo_name,
            compose_dir=cls.compose_dir,
            databases_csv=cls.databases_csv,
            database_containers=[cls.pg_container],
            images_no_stop_required=[POSTGRES_IMAGE],
        )
        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)
        cls.dump = (
            backup_path(cls.backups_dir, cls.repo_name, cls.version, cls.pg_volume)
            / "sql"
            / f"{cls.pg_container}.cluster.backup.sql"
        )

        for statement in DROP_SQL:
            cls._psql("postgres", statement)

        run(
            [
                "baudolo-restore",
                "cluster",
                cls.pg_volume,
                cls.hash,
                cls.version,
                "--backups-dir",
                cls.backups_dir,
                "--repo-name",
                cls.repo_name,
                "--container",
                cls.pg_container,
                "--instance",
                cls.pg_container,
                "--db-user",
                "postgres",
                "--db-password",
                "pgpw",
                "--empty",
            ]
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    @classmethod
    def _psql(cls, database: str, sql: str) -> str:
        p = run(
            [
                "docker",
                "exec",
                cls.pg_container,
                "sh",
                "-lc",
                f'psql -U postgres -d {database} -t -A -c "{sql}"',
            ]
        )
        return (p.stdout or "").strip()

    def test_the_backup_wrote_a_cluster_dump(self) -> None:
        self.assertTrue(self.dump.is_file(), f"no cluster dump at {self.dump}")

    def test_both_databases_are_back(self) -> None:
        listed = self._psql(
            "postgres",
            "SELECT datname FROM pg_database WHERE datname IN ('first','second') ORDER BY 1",
        )
        self.assertEqual(listed.split(), ["first", "second"])

    def test_each_database_carries_its_own_payload(self) -> None:
        self.assertEqual(self._psql("first", "SELECT v FROM t"), "first-payload")
        self.assertEqual(self._psql("second", "SELECT v FROM t"), "second-payload")

    def test_the_superusers_own_create_was_filtered(self) -> None:
        self.assertEqual(
            self._psql(
                "postgres", "SELECT rolsuper FROM pg_roles WHERE rolname = 'postgres'"
            ),
            "t",
        )

    def test_the_owning_role_is_back(self) -> None:
        self.assertEqual(
            self._psql(
                "postgres", "SELECT rolname FROM pg_roles WHERE rolname = 'app'"
            ),
            "app",
        )

    def test_ownership_survived(self) -> None:
        self.assertEqual(
            self._psql(
                "postgres",
                "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = 'first'",
            ),
            "app",
        )


if __name__ == "__main__":
    unittest.main()
