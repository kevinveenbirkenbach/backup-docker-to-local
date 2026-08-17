import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from baudolo.restore.db import cluster as cluster_mod
from baudolo.restore.db import mariadb as mdb_mod
from baudolo.restore.db import postgres as pg_mod
from baudolo.restore.db import version as ver

POSTGRES_HEADER = """--
-- PostgreSQL database dump
--

\\restrict BbyzwODc1rWKL3rDyLhEjgCF0Kf2TU5ma7gcTs8eQI7copLtydXkc61zdULsPav

-- Dumped from database version 17.11
-- Dumped by pg_dump version 17.11

SET statement_timeout = 0;
"""

MARIADB_HEADER = """/*M!999999\\- enable the sandbox mode */
-- MariaDB dump 10.19-11.8.8-MariaDB, for debian-linux-gnu (x86_64)
--
-- Host: 127.0.0.1    Database: mysql
-- ------------------------------------------------------
-- Server version\t11.8.8-MariaDB-ubu2404

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
"""


def cluster_header(roles: int) -> str:
    """A pg_dumpall stream: banner, N roles, then the first database's dump."""
    head = [
        "--",
        "-- PostgreSQL database cluster dump",
        "--",
        "",
        "SET default_transaction_read_only = off;",
        "",
        "--",
        "-- Roles",
        "--",
    ]
    for i in range(roles):
        head.append(f'CREATE ROLE "app{i}";')
        head.append(f'ALTER ROLE "app{i}" WITH NOSUPERUSER INHERIT LOGIN;')
    head.append("\\connect app")
    head.append("")
    return "\n".join(head) + "\n" + POSTGRES_HEADER


def dump_file(text: str) -> str:
    path = os.path.join(tempfile.mkdtemp(), "app.backup.sql")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


class TestDumpVersion(unittest.TestCase):
    """Headers captured from postgres:17-alpine and mariadb:11 themselves."""

    def test_postgres_reads_the_source_server(self) -> None:
        self.assertEqual(
            ver.dump_version(dump_file(POSTGRES_HEADER), "postgres"), "17.11"
        )

    def test_mariadb_reads_the_server_not_the_dump_tool(self) -> None:
        found = ver.dump_version(dump_file(MARIADB_HEADER), "mariadb")
        self.assertEqual(found, "11.8.8-MariaDB-ubu2404")
        self.assertNotEqual(
            ver.major_of(found),
            10,
            "10.19 is mariadb-dump's own version, not the server's",
        )

    def test_cluster_dump_states_its_version_far_below_the_header(self) -> None:
        path = dump_file(cluster_header(roles=200))
        with open(path, encoding="utf-8") as handle:
            offset = next(i for i, line in enumerate(handle) if "Dumped from" in line)
        self.assertGreater(offset, 100, "fixture must exercise the deep scan")
        self.assertEqual(ver.dump_version(path, "postgres"), "17.11")

    def test_a_version_beyond_the_scan_limit_is_refused_not_ignored(self) -> None:
        path = dump_file(cluster_header(roles=ver.SCAN_LINES))
        with self.assertRaises(ver.VersionMismatch):
            ver.dump_version(path, "postgres")

    def test_a_dump_without_a_version_header_is_refused(self) -> None:
        path = dump_file("CREATE TABLE t (id int);\n")
        with self.assertRaises(ver.VersionMismatch):
            ver.dump_version(path, "postgres")


class TestMajorOf(unittest.TestCase):
    def test_reads_the_leading_number(self) -> None:
        self.assertEqual(ver.major_of("17.11"), 17)
        self.assertEqual(ver.major_of("11.8.8-MariaDB-ubu2404"), 11)
        self.assertEqual(ver.major_of("9.6.24"), 9)
        self.assertEqual(ver.major_of("18beta1"), 18)

    def test_refuses_an_unreadable_version(self) -> None:
        with self.assertRaises(ver.VersionMismatch):
            ver.major_of("unknown")


class TestAssertReplayable(unittest.TestCase):
    def test_newer_dump_into_older_engine_is_refused(self) -> None:
        with self.assertRaises(ver.VersionMismatch) as caught:
            ver.assert_replayable("/b/app.sql", "postgres", "17.11", "15.6")
        self.assertIn("17.11", str(caught.exception))
        self.assertIn("15.6", str(caught.exception))

    def test_same_major_passes(self) -> None:
        ver.assert_replayable("/b/app.sql", "postgres", "17.4", "17.11")

    def test_older_dump_into_newer_engine_passes(self) -> None:
        ver.assert_replayable("/b/app.sql", "postgres", "15.6", "17.11")


class TestServerVersion(unittest.TestCase):
    def test_postgres_asks_over_pgpassword(self) -> None:
        with patch.object(ver, "docker_exec") as exec_:
            exec_.return_value = MagicMock(stdout=b" 17.11 \n")
            found = ver.server_version("db", "postgres", "app", "pw")
        self.assertEqual(found, "17.11")
        argv = exec_.call_args.args[1]
        self.assertIn("SHOW server_version", argv)
        self.assertEqual(exec_.call_args.kwargs["docker_env"], {"PGPASSWORD": "pw"})

    def test_mariadb_asks_through_the_detected_client(self) -> None:
        with patch.object(ver, "docker_exec") as exec_:
            exec_.return_value = MagicMock(stdout=b"11.8.8-MariaDB-ubu2404\n")
            found = ver.server_version("db", "mariadb", "app", "pw", client="mysql")
        self.assertEqual(found, "11.8.8-MariaDB-ubu2404")
        self.assertEqual(exec_.call_args.args[1][0], "mysql")


class TestGateStopsBeforeDestroying(unittest.TestCase):
    """--empty drops in one session and replays in the next, with no rollback
    between them, so the refusal has to land before the first session."""

    def setUp(self) -> None:
        self.serving = patch.object(ver, "docker_exec").start()
        self.addCleanup(patch.stopall)

    def serve(self, version: str) -> None:
        self.serving.return_value = MagicMock(stdout=version.encode())

    def test_postgres_refuses_without_running_the_preclean(self) -> None:
        self.serve("15.6")
        path = dump_file(POSTGRES_HEADER)
        with (
            patch.object(pg_mod, "docker_exec") as replay,
            self.assertRaises(ver.VersionMismatch),
        ):
            pg_mod.restore_postgres_sql(
                container="db",
                db_name="app",
                user="app",
                password="pw",
                sql_path=path,
                empty=True,
            )
        replay.assert_not_called()

    def test_cluster_refuses_without_running_the_preclean(self) -> None:
        self.serve("15.6")
        path = dump_file(cluster_header(roles=3))
        with (
            patch.object(cluster_mod, "docker_exec") as replay,
            self.assertRaises(ver.VersionMismatch),
        ):
            cluster_mod.restore_cluster_sql(
                container="db",
                user="postgres",
                password="pw",
                sql_path=path,
                empty=True,
            )
        replay.assert_not_called()

    def test_mariadb_refuses_without_dropping_tables(self) -> None:
        self.serve("10.11.6-MariaDB")
        path = dump_file(MARIADB_HEADER)
        with (
            patch.object(mdb_mod, "_pick_client", return_value="mariadb"),
            patch.object(mdb_mod, "docker_exec") as replay,
            self.assertRaises(ver.VersionMismatch),
        ):
            mdb_mod.restore_mariadb_sql(
                container="db",
                db_name="app",
                user="app",
                password="pw",
                sql_path=path,
                empty=True,
            )
        replay.assert_not_called()

    def test_matching_versions_let_the_replay_through(self) -> None:
        self.serve("17.11")
        path = dump_file(POSTGRES_HEADER)
        with patch.object(pg_mod, "docker_exec") as replay:
            pg_mod.restore_postgres_sql(
                container="db",
                db_name="app",
                user="app",
                password="pw",
                sql_path=path,
                empty=False,
            )
        replay.assert_called_once()

    def test_the_escape_hatch_asks_the_engine_nothing(self) -> None:
        path = dump_file("CREATE TABLE t (id int);\n")
        with patch.object(pg_mod, "docker_exec"):
            pg_mod.restore_postgres_sql(
                container="db",
                db_name="app",
                user="app",
                password="pw",
                sql_path=path,
                empty=False,
                check_version=False,
            )
        self.serving.assert_not_called()

    def test_a_missing_dump_is_reported_as_missing_not_as_a_mismatch(self) -> None:
        with self.assertRaises(FileNotFoundError):
            pg_mod.restore_postgres_sql(
                container="db",
                db_name="app",
                user="app",
                password="pw",
                sql_path=os.path.join(tempfile.mkdtemp(), "absent.sql"),
                empty=True,
            )


if __name__ == "__main__":
    unittest.main()
