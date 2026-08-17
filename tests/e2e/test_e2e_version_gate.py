"""A dump from a newer engine must be refused before --empty destroys anything.

The pre-clean and the replay are two separate sessions with no rollback across
them, so a dump the engine cannot parse leaves an emptied database behind. The
decisive assertion here is not the non-zero exit - it is that the payload is
still readable afterwards.
"""

import re
import unittest
from pathlib import Path

from .helpers import (
    MARIADB_DATA_DIR,
    MARIADB_IMAGE,
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
    wait_for_mariadb,
    wait_for_mariadb_sql,
    wait_for_postgres,
    write_databases_csv,
)

PAYLOAD = "gate-payload"
FUTURE = "99.0"


def rewrite_version(dump: Path, pattern: str, version: str) -> str:
    """Make the dump claim ``version``; return what it claimed before."""
    text = dump.read_text(encoding="utf-8", errors="replace")
    found = re.search(pattern, text)
    if not found:
        raise AssertionError(f"{dump} carries no version header matching {pattern}")
    claimed = found.group(1)
    dump.write_text(
        text.replace(found.group(0), found.group(0).replace(claimed, version), 1),
        encoding="utf-8",
    )
    return claimed


class GateCase:
    """Drive one engine through refusal, escape hatch and truthful replay."""

    engine = ""
    pattern = ""

    @classmethod
    def restore(cls, *extra: str):
        return run(
            [
                "baudolo-restore",
                cls.engine,
                cls.volume,
                cls.hash,
                cls.version,
                "--backups-dir",
                cls.backups_dir,
                "--repo-name",
                cls.repo_name,
                "--container",
                cls.container,
                "--db-name",
                cls.db_name,
                "--db-user",
                cls.db_user,
                "--db-password",
                cls.db_password,
                "--empty",
                *extra,
            ],
            check=False,
        )

    @classmethod
    def prepare(cls) -> None:
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)
        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix
        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(
            cls.databases_csv,
            [(cls.container, cls.db_name, cls.db_user, cls.db_password)],
        )
        backup_run(
            backups_dir=cls.backups_dir,
            repo_name=cls.repo_name,
            compose_dir=cls.compose_dir,
            databases_csv=cls.databases_csv,
            database_containers=[cls.container],
            images_no_stop_required=[cls.image],
        )
        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)
        cls.dump = (
            backup_path(cls.backups_dir, cls.repo_name, cls.version, cls.volume)
            / "sql"
            / f"{cls.db_name}.backup.sql"
        )

        cls.truthful_version = rewrite_version(cls.dump, cls.pattern, FUTURE)
        cls.refused = cls.restore()
        cls.payload_after_refusal = cls.read_payload()

        cls.forced = cls.restore("--no-version-check")
        cls.payload_after_force = cls.read_payload()

        rewrite_version(cls.dump, cls.pattern, cls.truthful_version)
        cls.replayed = cls.restore()
        cls.payload_after_replay = cls.read_payload()

    def test_the_dump_states_the_engine_it_came_from(self) -> None:
        self.assertRegex(self.truthful_version, r"^\d+")

    def test_a_newer_dump_is_refused(self) -> None:
        self.assertNotEqual(self.refused.returncode, 0, self.refused.stdout)

    def test_the_refusal_names_the_version_it_refused(self) -> None:
        self.assertIn(FUTURE, self.refused.stderr)
        self.assertIn("older engine", self.refused.stderr)

    def test_the_refusal_left_the_data_untouched(self) -> None:
        self.assertEqual(
            self.payload_after_refusal,
            PAYLOAD,
            "--empty pre-cleaned before the version was checked",
        )

    def test_the_escape_hatch_replays_anyway(self) -> None:
        self.assertEqual(self.forced.returncode, 0, self.forced.stderr)
        self.assertEqual(self.payload_after_force, PAYLOAD)

    def test_a_truthful_dump_replays(self) -> None:
        self.assertEqual(self.replayed.returncode, 0, self.replayed.stderr)
        self.assertEqual(self.payload_after_replay, PAYLOAD)


class TestE2EPostgresVersionGate(GateCase, unittest.TestCase):
    engine = "postgres"
    pattern = r"-- Dumped from database version (\S+)"

    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-pg-gate")
        cls.container = f"{cls.prefix}-pg"
        cls.volume = f"{cls.prefix}-pg-vol"
        cls.image = POSTGRES_IMAGE
        cls.db_name = "appdb"
        cls.db_user = "postgres"
        cls.db_password = "pgpw"

        run(["docker", "volume", "create", cls.volume])
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cls.container,
                "-e",
                f"POSTGRES_PASSWORD={cls.db_password}",
                "-v",
                f"{cls.volume}:{POSTGRES_DATA_DIR}",
                POSTGRES_IMAGE,
            ]
        )
        wait_for_postgres(cls.container, user=cls.db_user)
        cls.sql("postgres", f"CREATE DATABASE {cls.db_name}")
        cls.sql(
            cls.db_name,
            f"CREATE TABLE t (v text); INSERT INTO t VALUES ('{PAYLOAD}');",
        )
        cls.prepare()

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=[cls.container], volumes=[cls.volume])

    @classmethod
    def sql(cls, database: str, statement: str) -> str:
        p = run(
            [
                "docker",
                "exec",
                cls.container,
                "sh",
                "-lc",
                f'psql -U {cls.db_user} -d {database} -t -A -c "{statement}"',
            ],
            check=False,
        )
        return (p.stdout or "").strip()

    @classmethod
    def read_payload(cls) -> str:
        return cls.sql(cls.db_name, "SELECT v FROM t")


class TestE2EMariadbVersionGate(GateCase, unittest.TestCase):
    engine = "mariadb"
    pattern = r"-- Server version\s+(\S+)"

    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-mdb-gate")
        cls.container = f"{cls.prefix}-mdb"
        cls.volume = f"{cls.prefix}-mdb-vol"
        cls.image = MARIADB_IMAGE
        cls.db_name = "appdb"
        cls.db_user = "test"
        cls.db_password = "testpw"

        run(["docker", "volume", "create", cls.volume])
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cls.container,
                "-e",
                "MARIADB_ROOT_PASSWORD=rootpw",
                "-e",
                f"MARIADB_DATABASE={cls.db_name}",
                "-e",
                f"MARIADB_USER={cls.db_user}",
                "-e",
                f"MARIADB_PASSWORD={cls.db_password}",
                "-v",
                f"{cls.volume}:{MARIADB_DATA_DIR}",
                MARIADB_IMAGE,
            ]
        )
        wait_for_mariadb(cls.container, root_password="rootpw", timeout_s=90)
        wait_for_mariadb_sql(
            cls.container, user=cls.db_user, password=cls.db_password, timeout_s=90
        )
        cls.sql(
            f"CREATE TABLE {cls.db_name}.t (v VARCHAR(50)); "
            f"INSERT INTO {cls.db_name}.t VALUES ('{PAYLOAD}');"
        )
        cls.prepare()

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=[cls.container], volumes=[cls.volume])

    @classmethod
    def sql(cls, statement: str) -> str:
        p = run(
            [
                "docker",
                "exec",
                cls.container,
                "sh",
                "-lc",
                (
                    f"mariadb -h 127.0.0.1 -u{cls.db_user} -p{cls.db_password} "
                    f'-N -B -e "{statement}"'
                ),
            ],
            check=False,
        )
        return (p.stdout or "").strip()

    @classmethod
    def read_payload(cls) -> str:
        return cls.sql(f"SELECT v FROM {cls.db_name}.t")


if __name__ == "__main__":
    unittest.main()
