import contextlib
import io
import unittest
from unittest.mock import patch

from baudolo.restore import __main__ as cli

BASE = [
    "postgres",
    "app_vol",
    "hash",
    "20260817000000",
    "--repo-name",
    "repo",
    "--container",
    "db",
    "--db-name",
    "app",
]


class TestRestorePasswordChannel(unittest.TestCase):
    def call(self, extra, stdin=""):
        stderr = io.StringIO()
        with (
            patch.object(cli, "restore_postgres_sql") as restore,
            patch.object(cli, "locate", side_effect=lambda path: path),
            patch("sys.stdin", io.StringIO(stdin)),
            contextlib.redirect_stderr(stderr),
        ):
            code = cli.main([*BASE, *extra])
        return code, restore, stderr.getvalue()

    def test_stdin_carries_the_password_without_its_newline(self):
        code, restore, stderr = self.call(["--db-password-stdin"], stdin="s3cret\n")
        self.assertEqual(code, 0)
        self.assertEqual(restore.call_args.kwargs["password"], "s3cret")
        self.assertNotIn("WARNING", stderr)

    def test_the_argument_still_works_but_warns(self):
        code, restore, stderr = self.call(["--db-password", "s3cret"])
        self.assertEqual(code, 0)
        self.assertEqual(restore.call_args.kwargs["password"], "s3cret")
        self.assertIn("visible in the process list", stderr)

    def test_both_ways_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as caught:
            self.call(["--db-password", "x", "--db-password-stdin"], stdin="y")
        self.assertEqual(caught.exception.code, 2)

    def test_neither_way_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as caught:
            self.call([])
        self.assertEqual(caught.exception.code, 2)

    def test_files_needs_no_password(self):
        with patch.object(cli, "restore_volume_files", return_value=0) as restore:
            code = cli.main(
                ["files", "app_vol", "hash", "20260817000000", "--repo-name", "repo"]
            )
        self.assertEqual(code, 0)
        restore.assert_called_once()


if __name__ == "__main__":
    unittest.main()
