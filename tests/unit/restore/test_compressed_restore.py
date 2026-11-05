import gzip
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from baudolo.restore import run as run_mod
from baudolo.restore.db import cluster as cluster_mod
from baudolo.restore.db import mariadb as mdb_mod
from baudolo.restore.db import postgres as pg_mod
from baudolo.restore.db import version as ver
from baudolo.restore.dumpfile import is_gzip, locate, open_dump, verify
from baudolo.restore.paths import BackupPaths

from .test_version_gate import MARIADB_HEADER, POSTGRES_HEADER, cluster_header

SQL = (
    POSTGRES_HEADER + "CREATE TABLE t (id int);\nINSERT INTO t VALUES (1);\n"
).encode()


def write(directory: Path, name: str, data: bytes) -> str:
    path = directory / name
    path.write_bytes(data)
    return str(path)


class DumpCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())


class TestOpenDump(DumpCase):
    def test_gzip_and_plain_read_the_same_sql(self):
        packed = write(self.dir, "a.backup.sql.gz", gzip.compress(SQL))
        plain = write(self.dir, "b.backup.sql", SQL)
        for path in (packed, plain):
            with self.subTest(path=path), open_dump(path) as handle:
                self.assertEqual(handle.read(), SQL)

    def test_the_magic_decides_not_the_name(self):
        misnamed = write(self.dir, "c.backup.sql", gzip.compress(SQL))
        self.assertTrue(is_gzip(misnamed))
        with open_dump(misnamed) as handle:
            self.assertEqual(handle.read(), SQL)


class TestLocate(DumpCase):
    def test_the_compressed_name_wins_when_alone(self):
        path = write(self.dir, "db.backup.sql.gz", gzip.compress(SQL))
        self.assertEqual(locate(path), path)

    def test_an_old_uncompressed_dump_is_found(self):
        legacy = write(self.dir, "db.backup.sql", SQL)
        self.assertEqual(locate(str(self.dir / "db.backup.sql.gz")), legacy)

    def test_both_present_is_refused(self):
        write(self.dir, "db.backup.sql", SQL)
        path = write(self.dir, "db.backup.sql.gz", gzip.compress(SQL))
        with self.assertRaises(FileExistsError):
            locate(path)

    def test_neither_present_names_both(self):
        with self.assertRaises(FileNotFoundError) as caught:
            locate(str(self.dir / "db.backup.sql.gz"))
        self.assertIn("db.backup.sql.gz", str(caught.exception))
        self.assertIn("db.backup.sql ", str(caught.exception) + " ")

    def test_the_path_helper_names_what_this_version_writes(self):
        paths = BackupPaths("vol", "h", "v", repo_name="r", backups_dir="/B")
        self.assertEqual(paths.sql_file("app"), "/B/h/r/v/vol/sql/app.backup.sql.gz")


class TestVerify(DumpCase):
    def test_a_sound_gzip_and_a_plain_file_pass(self):
        verify(write(self.dir, "a.gz", gzip.compress(SQL)))
        verify(write(self.dir, "b.sql", SQL[:10]))

    def test_a_truncated_gzip_is_refused(self):
        packed = gzip.compress(SQL * 50)
        with self.assertRaises(EOFError):
            verify(write(self.dir, "t.gz", packed[: len(packed) // 2]))

    def test_a_corrupt_gzip_is_refused(self):
        packed = bytearray(gzip.compress(SQL * 50))
        packed[-6] ^= 0xFF
        with self.assertRaises((gzip.BadGzipFile, zlib.error, EOFError)):
            verify(write(self.dir, "c.gz", bytes(packed)))


class TestReadersAcceptGzip(DumpCase):
    def test_the_version_header_is_read_through_gzip(self):
        for header, engine, expected in (
            (POSTGRES_HEADER, "postgres", "17.11"),
            (MARIADB_HEADER, "mariadb", "11.8.8-MariaDB-ubu2404"),
        ):
            with self.subTest(engine=engine):
                path = write(self.dir, f"{engine}.gz", gzip.compress(header.encode()))
                self.assertEqual(ver.dump_version(path, engine), expected)

    def test_the_cluster_inventory_is_read_through_gzip(self):
        data = (cluster_header(roles=2) + "CREATE DATABASE app2;\n").encode()
        path = write(self.dir, "c.cluster.backup.sql.gz", gzip.compress(data))
        databases, roles = cluster_mod.dump_inventory(path)
        self.assertIn("app2", databases)
        self.assertEqual(roles, ["app0", "app1"])


class TestReplayFeedsSql(DumpCase):
    def test_postgres_replays_decompressed_sql(self):
        fed = []

        def capture(container, argv, **kwargs):
            stdin = kwargs.get("stdin")
            fed.append(stdin if isinstance(stdin, bytes) else stdin.read())
            return MagicMock()

        for name, data in (
            ("new.backup.sql.gz", gzip.compress(SQL)),
            ("old.backup.sql", SQL),
        ):
            fed.clear()
            path = write(self.dir, name, data)
            with (
                self.subTest(name=name),
                patch.object(pg_mod, "docker_exec", side_effect=capture),
            ):
                pg_mod.restore_postgres_sql(
                    container="db",
                    db_name="app",
                    user="app",
                    password="pw",
                    sql_path=path,
                    empty=False,
                    check_version=False,
                )
                self.assertEqual(fed, [SQL])

    def test_mariadb_streams_decompressed_sql(self):
        fed = []

        def capture(container, argv, *, source, docker_env):
            fed.append(source.read())

        for name, data in (
            ("new.backup.sql.gz", gzip.compress(SQL)),
            ("old.backup.sql", SQL),
        ):
            fed.clear()
            path = write(self.dir, name, data)
            with (
                self.subTest(name=name),
                patch.object(mdb_mod, "_pick_client", return_value="mariadb"),
                patch.object(mdb_mod, "docker_exec_stream", side_effect=capture),
            ):
                mdb_mod.restore_mariadb_sql(
                    container="db",
                    db_name="app",
                    user="app",
                    password="pw",
                    sql_path=path,
                    empty=False,
                    check_version=False,
                )
                self.assertEqual(fed, [SQL])

    def test_the_stream_reaches_the_child_decompressed(self):
        out = self.dir / "received.sql"
        sink = "import shutil, sys; shutil.copyfileobj(sys.stdin.buffer, open(sys.argv[1], 'wb'))"
        path = write(self.dir, "s.gz", gzip.compress(SQL * 2000))
        with (
            patch.object(
                run_mod,
                "docker_exec_cmd",
                return_value=[sys.executable, "-c", sink, str(out)],
            ),
            open_dump(path) as source,
        ):
            run_mod.docker_exec_stream("db", ["ignored"], source=source)
        self.assertEqual(out.read_bytes(), SQL * 2000)

    def test_a_child_that_dies_early_is_reported_by_its_exit_code(self):
        path = write(self.dir, "s.gz", gzip.compress(SQL * 20000))
        with (
            patch.object(
                run_mod,
                "docker_exec_cmd",
                return_value=[sys.executable, "-c", "import sys; sys.exit(3)"],
            ),
            open_dump(path) as source,
            patch("sys.stderr"),
            self.assertRaises(run_mod.subprocess.CalledProcessError) as caught,
        ):
            run_mod.docker_exec_stream("db", ["ignored"], source=source)
        self.assertEqual(caught.exception.returncode, 3)


class TestCorruptionStopsBeforeDestroying(DumpCase):
    def truncated(self) -> str:
        packed = gzip.compress(SQL * 500)
        return write(self.dir, "x.backup.sql.gz", packed[: len(packed) // 2])

    def test_postgres_runs_no_preclean_on_a_truncated_dump(self):
        with (
            patch.object(pg_mod, "docker_exec") as exec_,
            self.assertRaises(EOFError),
        ):
            pg_mod.restore_postgres_sql(
                container="db",
                db_name="app",
                user="app",
                password="pw",
                sql_path=self.truncated(),
                empty=True,
                check_version=False,
            )
        exec_.assert_not_called()

    def test_mariadb_drops_nothing_on_a_truncated_dump(self):
        with (
            patch.object(mdb_mod, "_pick_client", return_value="mariadb"),
            patch.object(mdb_mod, "docker_exec") as exec_,
            patch.object(mdb_mod, "docker_exec_stream") as stream,
            self.assertRaises(EOFError),
        ):
            mdb_mod.restore_mariadb_sql(
                container="db",
                db_name="app",
                user="app",
                password="pw",
                sql_path=self.truncated(),
                empty=True,
                check_version=False,
            )
        exec_.assert_not_called()
        stream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
