"""Which databases.csv instance a container name resolves to.

The cases are the container names real deployments produce, in both compose
and swarm, so a change to the regex has to state which shape it gives up.
"""

from __future__ import annotations

import unittest

from baudolo.backup.db import get_instance


class TestDeclaredContainers(unittest.TestCase):
    def test_a_declared_container_is_its_own_instance(self) -> None:
        self.assertEqual(
            get_instance("postgres-central", ["postgres-central"]), "postgres-central"
        )

    def test_a_declaration_beats_the_regex(self) -> None:
        """A declared name is taken whole even when it carries a token the
        fallback would otherwise strip."""
        self.assertEqual(
            get_instance("shop-database", ["shop-database"]), "shop-database"
        )

    def test_a_qualified_central_name_still_has_to_be_declared(self) -> None:
        self.assertIsNone(get_instance("postgres-central", []))


class TestContainersNamedAfterTheirEngine(unittest.TestCase):
    def test_a_bare_engine_name_is_its_own_instance(self) -> None:
        for name in ("postgres", "mariadb", "mysql", "db", "database"):
            with self.subTest(container=name):
                self.assertEqual(get_instance(name, []), name)

    def test_a_swarm_task_of_such_a_container_keeps_the_instance(self) -> None:
        self.assertEqual(get_instance("postgres_postgres.1.k3f9x2", []), "postgres")
        self.assertEqual(get_instance("mariadb_mariadb.1.k3f9x2", []), "mariadb")


class TestDedicatedEngines(unittest.TestCase):
    def test_compose_names_the_container_with_a_hyphen(self) -> None:
        self.assertEqual(get_instance("discourse-database", []), "discourse")

    def test_swarm_names_the_task_with_an_underscore_and_a_slot(self) -> None:
        """Swarm suppresses container_name and names the task
        <stack>_<service>.<slot>.<id>, which must land on the same instance as
        the compose name so one databases.csv serves both modes."""
        self.assertEqual(get_instance("discourse_database.1.k3f9x2", []), "discourse")

    def test_an_explicitly_named_engine_keeps_its_entity(self) -> None:
        self.assertEqual(get_instance("bigbluebutton-postgres-1", []), "bigbluebutton")

    def test_the_short_token_is_stripped_too(self) -> None:
        self.assertEqual(get_instance("matomo-db", []), "matomo")

    def test_mariadb_uses_the_same_suffix(self) -> None:
        self.assertEqual(get_instance("matomo-database", []), "matomo")

    def test_an_engine_named_suffix_is_stripped_too(self) -> None:
        self.assertEqual(get_instance("shop-mariadb", []), "shop")
        self.assertEqual(get_instance("shop-mysql", []), "shop")


class TestApplicationContainers(unittest.TestCase):
    def test_a_bare_application_name_is_not_a_database(self) -> None:
        """Returning the name unchanged here would offer the application as a
        second engine for its own dedicated database's instance."""
        self.assertIsNone(get_instance("discourse", []))

    def test_a_swarm_application_task_is_not_a_database(self) -> None:
        self.assertIsNone(get_instance("discourse_discourse.1.k3f9x2", []))

    def test_an_application_that_merely_starts_with_a_token_is_not_split(self) -> None:
        self.assertIsNone(get_instance("dbeaver", []))


if __name__ == "__main__":
    unittest.main()
