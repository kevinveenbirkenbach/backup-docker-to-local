import tempfile
import unittest
from unittest.mock import MagicMock, patch

from baudolo.restore.db import mariadb as mariadb_mod


class TestMariadbEmptyDrop(unittest.TestCase):
    def test_drops_run_in_one_session_with_fk_checks_off(self) -> None:
        calls = []

        def _capture(container, argv, **kwargs):
            calls.append(argv)
            result = MagicMock()
            result.stdout = b"users\nfetches\n"
            return result

        with tempfile.NamedTemporaryFile(suffix=".sql") as sql:
            sql.write(b"CREATE TABLE t (id int);\n")
            sql.flush()
            with (
                patch.object(mariadb_mod, "docker_exec", side_effect=_capture),
                patch.object(mariadb_mod, "_pick_client", return_value="mariadb"),
            ):
                mariadb_mod.restore_mariadb_sql(
                    container="db",
                    db_name="mailu",
                    user="mailu",
                    password="pw",
                    sql_path=sql.name,
                    empty=True,
                )

        drop_calls = [argv for argv in calls if any("DROP TABLE" in a for a in argv)]
        self.assertEqual(len(drop_calls), 1, f"expected ONE drop session: {calls}")
        drop_sql = drop_calls[0][-1]
        self.assertTrue(drop_sql.startswith("SET FOREIGN_KEY_CHECKS=0; "))
        self.assertIn("DROP TABLE IF EXISTS `mailu`.`users`;", drop_sql)
        self.assertIn("DROP TABLE IF EXISTS `mailu`.`fetches`;", drop_sql)
        self.assertTrue(drop_sql.endswith("SET FOREIGN_KEY_CHECKS=1;"))


if __name__ == "__main__":
    unittest.main()
