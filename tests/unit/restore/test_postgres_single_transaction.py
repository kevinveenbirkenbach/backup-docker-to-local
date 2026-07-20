import tempfile
import unittest
from unittest.mock import MagicMock, patch

from baudolo.restore.db import postgres as pg_mod


class TestPostgresSingleTransaction(unittest.TestCase):
    def test_replay_is_single_transaction_but_preclean_is_not(self) -> None:
        calls = []

        def _capture(container, argv, **kwargs):
            calls.append(argv)
            return MagicMock()

        with tempfile.NamedTemporaryFile(suffix=".sql") as sql:
            sql.write(b"CREATE TABLE t (id int);\nINSERT INTO t VALUES (1);\n")
            sql.flush()
            with patch.object(pg_mod, "docker_exec", side_effect=_capture):
                pg_mod.restore_postgres_sql(
                    container="db",
                    db_name="discourse",
                    user="discourse",
                    password="pw",
                    sql_path=sql.name,
                    empty=True,
                )

        self.assertEqual(len(calls), 2, f"expected pre-clean + replay: {calls}")
        preclean, replay = calls[0], calls[1]
        self.assertNotIn(
            "--single-transaction",
            preclean,
            "pre-clean must stay multi-statement or it exhausts max_locks on large schemas",
        )
        self.assertIn(
            "--single-transaction",
            replay,
            "dump replay must be atomic so a live concurrent writer cannot trip a duplicate-key abort",
        )


if __name__ == "__main__":
    unittest.main()
