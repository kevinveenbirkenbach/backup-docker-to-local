"""The --empty pre-clean drop must cover every object class a dump can
re-CREATE ahead of tables; a missed class aborts the replay under
ON_ERROR_STOP (OpenProject's ICU collation public.versions_name did)."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from baudolo.restore.db import postgres


class TestPostgresEmptyDrop(unittest.TestCase):
    def _drop_sql(self) -> str:
        with tempfile.NamedTemporaryFile(suffix=".sql") as fh:
            Path(fh.name).write_bytes(b"SELECT 1;\n")
            with mock.patch.object(postgres, "docker_exec") as run:
                postgres.restore_postgres_sql(
                    container="c",
                    db_name="db",
                    user="u",
                    password="p",
                    sql_path=fh.name,
                    empty=True,
                )
        first_call = run.call_args_list[0]
        return first_call.kwargs["stdin"].decode()

    def test_drop_covers_collations(self) -> None:
        sql = self._drop_sql()
        self.assertIn("pg_collation", sql)
        self.assertIn("'COLLATION' AS type", sql)
        self.assertIn("pg_get_userbyid(col.collowner) = current_user", sql)

    def test_drop_still_covers_the_other_classes(self) -> None:
        sql = self._drop_sql()
        for marker in ("pg_class", "pg_proc", "'SEQUENCE' AS type", "'TYPE' AS type"):
            self.assertIn(marker, sql)
        self.assertIn("DROP %s IF EXISTS public.%I CASCADE", sql)


if __name__ == "__main__":
    unittest.main()
