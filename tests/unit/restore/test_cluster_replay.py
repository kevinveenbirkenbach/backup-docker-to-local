import tempfile
import unittest
from unittest.mock import MagicMock, patch

from baudolo.restore.db import cluster as cluster_mod
from baudolo.restore.paths import BackupPaths


class TestClusterReplay(unittest.TestCase):
    def _replay(self, *, empty: bool):
        calls = []

        def _capture(container, argv, **kwargs):
            calls.append((argv, kwargs.get("stdin")))
            return MagicMock()

        with tempfile.NamedTemporaryFile(suffix=".sql") as sql:
            sql.write(b"CREATE ROLE app;\nCREATE DATABASE app OWNER app;\n")
            sql.flush()
            with patch.object(cluster_mod, "docker_exec", side_effect=_capture):
                cluster_mod.restore_cluster_sql(
                    container="db",
                    user="postgres",
                    password="pw",
                    sql_path=sql.name,
                    empty=empty,
                )
        return calls

    def test_the_replay_is_not_wrapped_in_a_transaction(self) -> None:
        argv, _ = self._replay(empty=False)[0]
        self.assertNotIn(
            "--single-transaction",
            argv,
            "CREATE DATABASE cannot run inside a transaction block, so unlike the "
            "single-database replay this stream must not be wrapped in one",
        )
        self.assertIn("ON_ERROR_STOP=1", argv)

    def test_the_replay_targets_the_control_database(self) -> None:
        argv, _ = self._replay(empty=False)[0]
        self.assertEqual(argv[argv.index("-d") + 1], cluster_mod.CONTROL_DB)
        self.assertEqual(argv[argv.index("-U") + 1], "postgres")

    def test_without_empty_nothing_is_dropped_first(self) -> None:
        self.assertEqual(len(self._replay(empty=False)), 1)

    def test_empty_drops_databases_before_their_owners(self) -> None:
        calls = self._replay(empty=True)
        self.assertEqual(len(calls), 2, f"expected pre-clean + replay: {calls}")
        preclean = calls[0][1].decode()
        self.assertLess(
            preclean.index("DROP DATABASE"),
            preclean.index("DROP ROLE"),
            "a role cannot be dropped while it still owns a database",
        )
        self.assertIn("DROP OWNED BY", preclean)
        self.assertIn("ORDER BY phase", preclean)

    def test_the_preclean_spares_what_the_dump_does_not_recreate(self) -> None:
        preclean = self._replay(empty=True)[0][1].decode()
        self.assertIn("NOT datistemplate", preclean)
        self.assertIn("datname <> current_database()", preclean)
        self.assertIn("starts_with(rolname, 'pg_')", preclean)
        self.assertIn("rolname <> current_user", preclean)

    def test_only_the_connecting_role_loses_its_create(self) -> None:
        # Captured from pg_dumpall 17: the bootstrap superuser is recreated like
        # any other role, and the pre-clean cannot drop the one holding the
        # session - so that single CREATE always collides while its ALTER, which
        # carries the attributes and the password, must survive.
        dump = [
            b"CREATE ROLE app;\n",
            b"ALTER ROLE app WITH NOSUPERUSER INHERIT LOGIN PASSWORD 'SCRAM-SHA-256$...';\n",
            b"CREATE ROLE postgres;\n",
            b"ALTER ROLE postgres WITH SUPERUSER INHERIT LOGIN PASSWORD 'SCRAM-SHA-256$...';\n",
            b'CREATE ROLE "odd-name";\n',
        ]
        kept = list(cluster_mod.filter_own_role_creation(dump, "postgres"))
        self.assertNotIn(b"CREATE ROLE postgres;\n", kept)
        self.assertIn(b"CREATE ROLE app;\n", kept)
        self.assertIn(b'CREATE ROLE "odd-name";\n', kept)
        self.assertEqual(
            sum(1 for line in kept if line.startswith(b"ALTER ROLE postgres")),
            1,
            "the ALTER re-applies the superuser's attributes and password",
        )

    def test_a_quoted_connecting_role_is_matched_too(self) -> None:
        kept = list(
            cluster_mod.filter_own_role_creation(
                [b'CREATE ROLE "odd-name";\n'], "odd-name"
            )
        )
        self.assertEqual(kept, [])

    def test_a_role_whose_name_merely_starts_the_same_is_kept(self) -> None:
        kept = list(
            cluster_mod.filter_own_role_creation(
                [b"CREATE ROLE postgresql;\n"], "postgres"
            )
        )
        self.assertEqual(kept, [b"CREATE ROLE postgresql;\n"])

    def test_a_missing_dump_is_reported_as_such(self) -> None:
        with self.assertRaises(FileNotFoundError):
            cluster_mod.restore_cluster_sql(
                container="db",
                user="postgres",
                password="pw",
                sql_path="/nonexistent/x.cluster.backup.sql",
                empty=False,
            )

    def test_the_path_helper_names_the_dumpall_file(self) -> None:
        paths = BackupPaths("vol", "hash", "v1", repo_name="repo", backups_dir="/B")
        self.assertEqual(
            paths.cluster_file("bigbluebutton"),
            "/B/hash/repo/v1/vol/sql/bigbluebutton.cluster.backup.sql",
        )


if __name__ == "__main__":
    unittest.main()
