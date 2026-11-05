import contextlib
import gzip
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from baudolo.backup import shell
from baudolo.backup.shell import BackupError, execute_to_gzip

CAT = (
    "import shutil, sys; shutil.copyfileobj(open(sys.argv[1], 'rb'), sys.stdout.buffer)"
)


def sql_lines(count: int, changed: int = -1) -> bytes:
    return b"".join(
        (
            b"INSERT INTO t VALUES (%d, 'changed');\n" % i
            if i == changed
            else b"INSERT INTO t VALUES (%d, 'name-%d');\n" % (i, i * 7919)
        )
        for i in range(count)
    )


def common_suffix(a: bytes, b: bytes) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


class GzipDumpCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def dump(self, payload: bytes, name: str = "db.backup.sql.gz") -> bytes:
        src = self.dir / f"{name}.src"
        src.write_bytes(payload)
        out = self.dir / name
        with contextlib.redirect_stdout(io.StringIO()):
            execute_to_gzip([sys.executable, "-c", CAT, str(src)], str(out))
        return out.read_bytes()


class TestRoundTrip(GzipDumpCase):
    def test_the_dump_round_trips_through_gzip(self):
        payload = sql_lines(5000) + b"-- " + b"x" * (3 * shell.READ_BYTES) + b"\n"
        packed = self.dump(payload)
        self.assertEqual(packed[:2], b"\x1f\x8b")
        self.assertEqual(gzip.decompress(packed), payload)

    def test_an_empty_dump_is_a_valid_empty_gzip(self):
        self.assertEqual(gzip.decompress(self.dump(b"")), b"")

    def test_no_temporary_file_is_left_behind(self):
        self.dump(sql_lines(10))
        self.assertEqual(sorted(p.suffix for p in self.dir.iterdir()), [".gz", ".src"])


class TestDeterminism(GzipDumpCase):
    def test_identical_dumps_give_identical_bytes(self):
        payload = sql_lines(20000)
        self.assertEqual(self.dump(payload, "a.gz"), self.dump(payload, "b.gz"))

    def test_the_header_carries_neither_a_name_nor_a_time(self):
        packed = self.dump(sql_lines(10))
        self.assertEqual(packed[3] & 0x08, 0, "FNAME flag set")
        self.assertEqual(packed[4:8], b"\x00\x00\x00\x00", "MTIME set")


class TestResync(GzipDumpCase):
    def test_a_change_near_the_start_leaves_the_tail_identical(self):
        before = sql_lines(100000)
        after = sql_lines(100000, changed=5)
        ours = common_suffix(
            self.dump(before, "a.gz")[:-8], self.dump(after, "b.gz")[:-8]
        )
        plain = common_suffix(gzip.compress(before)[:-8], gzip.compress(after)[:-8])
        self.assertLess(plain, 1024, "control: plain gzip must not resync")
        self.assertGreater(ours, len(gzip.compress(before)) // 2)


class TestFailure(GzipDumpCase):
    def test_a_failing_command_leaves_no_file(self):
        out = self.dir / "db.backup.sql.gz"
        script = "import sys; sys.stdout.write('partial'); sys.exit(3)"
        with (
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaises(BackupError) as caught,
        ):
            execute_to_gzip([sys.executable, "-c", script], str(out))
        self.assertIn("Exit code: 3", str(caught.exception))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_a_write_error_kills_the_dump_and_leaves_no_file(self):
        src = self.dir / "src"
        src.write_bytes(sql_lines(200000))
        out = self.dir / "db.backup.sql.gz"
        with (
            patch.object(
                gzip.GzipFile, "write", side_effect=OSError(28, "No space left")
            ),
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaises(BackupError),
        ):
            execute_to_gzip([sys.executable, "-c", CAT, str(src)], str(out))
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["src"])

    def test_env_reaches_the_child_without_the_argv(self):
        out = self.dir / "env.gz"
        script = "import os, sys; sys.stdout.write(os.environ['MYSQL_PWD'])"
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            execute_to_gzip(
                [sys.executable, "-c", script], str(out), env={"MYSQL_PWD": "s3cret"}
            )
        self.assertEqual(gzip.decompress(out.read_bytes()), b"s3cret")
        self.assertNotIn("s3cret", printed.getvalue())


if __name__ == "__main__":
    unittest.main()
