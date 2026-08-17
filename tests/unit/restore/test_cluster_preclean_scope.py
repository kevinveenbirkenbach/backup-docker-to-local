"""The pre-clean may only drop what the dump can bring back.

A shared instance carries databases and roles from other applications, and a
database created after the backup is in no dump at all. Dropping those would
destroy data this restore cannot restore.
"""

import tempfile
import unittest
from pathlib import Path

from baudolo.restore.db import cluster as cluster_mod

DUMP = """--
-- PostgreSQL database cluster dump
--

CREATE ROLE app;
ALTER ROLE app WITH LOGIN;
CREATE ROLE reporting;

CREATE DATABASE appdb OWNER app;

\\connect appdb

CREATE TABLE t (v text);

\\connect template1
"""


def dump_file(text: str) -> str:
    path = Path(tempfile.mkdtemp()) / "central.cluster.backup.sql"
    path.write_text(text, encoding="utf-8")
    return str(path)


class TestDumpInventory(unittest.TestCase):
    def test_it_reads_databases_and_roles_the_dump_recreates(self) -> None:
        databases, roles = cluster_mod.dump_inventory(dump_file(DUMP))
        self.assertEqual(databases, ["appdb", "template1"])
        self.assertEqual(roles, ["app", "reporting"])

    def test_a_quoted_name_keeps_its_spaces(self) -> None:
        databases, roles = cluster_mod.dump_inventory(
            dump_file('\\connect "odd name"\nCREATE ROLE "odd role";\n')
        )
        self.assertEqual(databases, ["odd name"])
        self.assertEqual(roles, ["odd role"])

    def test_psql_options_are_not_mistaken_for_the_database(self) -> None:
        databases, _roles = cluster_mod.dump_inventory(
            dump_file("\\connect -reuse-previous=on dbname=appdb\n")
        )
        self.assertEqual(databases, ["appdb"])

    def test_create_database_options_are_not_part_of_the_name(self) -> None:
        databases, _roles = cluster_mod.dump_inventory(
            dump_file("CREATE DATABASE appdb WITH TEMPLATE = template0 OWNER = app;\n")
        )
        self.assertEqual(databases, ["appdb"])

    def test_a_name_is_listed_once(self) -> None:
        databases, _roles = cluster_mod.dump_inventory(
            dump_file("\\connect a\n\\connect a\n")
        )
        self.assertEqual(databases, ["a"])


class TestInstanceRefusal(unittest.TestCase):
    """--empty wipes the whole instance, so it may only run on one this dump
    can rebuild. Scoping the sweep instead wedges the restore: a surviving
    database that grants to a dumped role pins it, DROP ROLE fails, and the
    pre-clean aborts after the dump's own databases are already gone."""

    def check(self, present: str, dump: str = DUMP):
        from unittest import mock

        with mock.patch.object(
            cluster_mod, "instance_databases", return_value=present.split()
        ):
            cluster_mod.assert_instance_matches_dump(
                "db", "postgres", dump_file(dump), {}
            )

    def test_an_instance_the_dump_covers_passes(self) -> None:
        self.check("appdb")

    def test_an_empty_instance_passes(self) -> None:
        self.check("")

    def test_a_database_the_dump_lacks_is_refused(self) -> None:
        with self.assertRaises(RuntimeError) as raised:
            self.check("appdb sibling")
        self.assertIn("sibling", str(raised.exception))

    def test_the_refusal_names_every_foreign_database(self) -> None:
        with self.assertRaises(RuntimeError) as raised:
            self.check("one two")
        message = str(raised.exception)
        self.assertIn("one", message)
        self.assertIn("two", message)

    def test_the_refusal_happens_before_anything_is_dropped(self) -> None:
        from unittest import mock

        with (
            mock.patch.object(
                cluster_mod, "instance_databases", return_value=["foreign"]
            ),
            mock.patch.object(cluster_mod, "docker_exec") as touched,
            self.assertRaises(RuntimeError),
        ):
            cluster_mod.restore_cluster_sql(
                container="db",
                user="postgres",
                password="pw",
                sql_path=dump_file(DUMP),
                empty=True,
                check_version=False,
            )
        touched.assert_not_called()


if __name__ == "__main__":
    unittest.main()
