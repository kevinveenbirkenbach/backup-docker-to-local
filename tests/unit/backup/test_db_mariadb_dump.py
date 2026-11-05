import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from baudolo.backup import db as db_mod


def _df(rows):
    return pd.DataFrame(rows, columns=["instance", "database", "username", "password"])


def _capture_dumps(*, db_type, rows, container, dump_tool="mariadb-dump"):
    """Every (argv, env) the dump path would have run."""
    captured = []

    def _capture(command, out_file, *, env=None):
        captured.append((list(command), env, out_file))

    with (
        tempfile.TemporaryDirectory() as td,
        patch.object(db_mod, "execute_to_file", side_effect=_capture),
    ):
        db_mod.backup_database(
            container=container,
            volume_dir=td,
            db_type=db_type,
            dump_tool=dump_tool,
            databases_df=_df(rows),
            database_containers=[container],
        )
    return captured


class TestMariaDBDumpUsesTCP(unittest.TestCase):
    # Regression guard for 'Access denied for user <user>@localhost' when only
    # '<user>'@'%' is granted: the in-container mariadb-dump MUST force TCP so
    # the connection is auth-matched against '%' instead of socket->localhost.

    def test_mariadb_dump_forces_tcp_loopback(self):
        captured = _capture_dumps(
            db_type="mariadb",
            rows=[("mariadb", "appdb", "appuser", "s3cret")],
            container="mariadb",
        )
        self.assertEqual(len(captured), 1, f"expected one dump, got: {captured}")

        argv, _env, _out = captured[0]
        self.assertEqual(argv[:2], ["docker", "exec"])
        self.assertEqual(argv[argv.index(dump_tool_of(argv)) - 1], "mariadb")
        self.assertIn("--protocol=tcp", argv)
        self.assertEqual(argv[argv.index("-h") + 1], "127.0.0.1")
        self.assertEqual(argv[argv.index("-u") + 1], "appuser")
        self.assertEqual(argv[-1], "appdb")

    def test_the_probed_client_is_the_one_invoked(self):
        captured = _capture_dumps(
            db_type="mariadb",
            rows=[("mariadb", "appdb", "appuser", "s3cret")],
            container="mariadb",
            dump_tool="mysqldump",
        )
        argv, _env, _out = captured[0]
        self.assertIn("mysqldump", argv)
        self.assertNotIn("mariadb-dump", argv)

    def test_postgres_dump_unaffected(self):
        captured = _capture_dumps(
            db_type="postgres",
            rows=[("pg", "appdb", "appuser", "s3cret")],
            container="pg",
        )
        argv, _env, _out = captured[0]
        self.assertIn("pg_dump", argv)
        self.assertNotIn("--protocol=tcp", argv)

    def test_the_password_travels_in_the_environment_not_the_argv(self):
        for db_type, container, variable in (
            ("postgres", "pg", "PGPASSWORD"),
            ("mariadb", "mariadb", "MYSQL_PWD"),
        ):
            with self.subTest(engine=db_type):
                argv, env, _out = _capture_dumps(
                    db_type=db_type,
                    rows=[(container, "appdb", "appuser", "s3cret")],
                    container=container,
                )[0]
                self.assertEqual(env, {variable: "s3cret"})
                self.assertEqual(argv[argv.index("-e") + 1], variable)
                self.assertLess(argv.index("-e"), argv.index(container))
                self.assertFalse(
                    [arg for arg in argv if "s3cret" in arg],
                    f"password reached the argv: {argv}",
                )


def dump_tool_of(argv):
    return next(arg for arg in argv if arg in ("mariadb-dump", "mysqldump"))


class TestNoShellReachesTheDump(unittest.TestCase):
    def test_a_hostile_database_name_never_reaches_a_command(self):
        """validate_database refuses it, so no argv is built at all."""
        with self.assertRaises(ValueError):
            _capture_dumps(
                db_type="postgres",
                rows=[("pg", "app;rm -rf /", "appuser", "s3cret")],
                container="pg",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
