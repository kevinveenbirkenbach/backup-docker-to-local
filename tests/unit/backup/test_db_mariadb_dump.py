import tempfile
import unittest
from unittest.mock import patch

import pandas

from baudolo.backup import db as db_mod


def _df(rows):
    return pandas.DataFrame(
        rows, columns=["instance", "database", "username", "password"]
    )


def _capture_commands(*, db_type, rows, container):
    captured = []

    def _capture(cmd):
        captured.append(cmd)
        return []

    with tempfile.TemporaryDirectory() as td:
        with patch.object(db_mod, "execute_shell_command", side_effect=_capture):
            db_mod.backup_database(
                container=container,
                volume_dir=td,
                db_type=db_type,
                databases_df=_df(rows),
                database_containers=[container],
            )
    return captured


class TestMariaDBDumpUsesTCP(unittest.TestCase):
    # Regression guard for 'Access denied for user <user>@localhost' when only
    # '<user>'@'%' is granted: the in-container mariadb-dump MUST force TCP so
    # the connection is auth-matched against '%' instead of socket->localhost.

    def test_mariadb_dump_forces_tcp_loopback(self):
        captured = _capture_commands(
            db_type="mariadb",
            rows=[("mariadb", "appdb", "appuser", "s3cret")],
            container="mariadb",
        )
        dump_cmds = [c for c in captured if "mariadb-dump" in c]
        self.assertEqual(
            len(dump_cmds), 1, f"expected one dump command, got: {captured}"
        )

        cmd = dump_cmds[0]
        self.assertIn("-h 127.0.0.1", cmd)
        self.assertIn("--protocol=tcp", cmd)
        self.assertIn("-u appuser", cmd)
        self.assertIn("-ps3cret", cmd)
        self.assertIn(" appdb", cmd)

    def test_postgres_dump_unaffected(self):
        captured = _capture_commands(
            db_type="postgres",
            rows=[("pg", "appdb", "appuser", "s3cret")],
            container="pg",
        )
        dump_cmds = [c for c in captured if "pg_dump" in c and "pg_dumpall" not in c]
        self.assertEqual(len(dump_cmds), 1)
        self.assertNotIn("--protocol=tcp", dump_cmds[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
