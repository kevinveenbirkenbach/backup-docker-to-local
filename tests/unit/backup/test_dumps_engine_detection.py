import unittest
from unittest.mock import patch

import pandas

from baudolo.backup import dumps as dumps_mod


def _df(rows):
    return pandas.DataFrame(
        rows, columns=["instance", "database", "username", "password"]
    )


class _Probe:
    def __init__(self, available, image="sha256:aaa"):
        self.available = set(available)
        self.image = image
        self.calls = []

    def has_tool(self, container, tool):
        self.calls.append((container, tool))
        return tool in self.available

    def image_id(self, container):
        return self.image if isinstance(self.image, str) else self.image[container]


def _detect(probe, container="c1"):
    dumps_mod._ENGINE_BY_IMAGE.clear()
    with (
        patch.object(dumps_mod, "has_tool", probe.has_tool),
        patch.object(dumps_mod, "image_id", probe.image_id),
    ):
        return dumps_mod.container_engine(container)


class TestContainerEngine(unittest.TestCase):
    def test_a_postgres_is_found_by_its_dump_tool(self):
        self.assertEqual(_detect(_Probe(["pg_dumpall"])), ("postgres", "pg_dumpall"))

    def test_a_mariadb_is_found_by_its_dump_tool(self):
        self.assertEqual(_detect(_Probe(["mariadb-dump"])), ("mariadb", "mariadb-dump"))

    def test_an_image_with_only_mysqldump_is_dumped_with_mysqldump(self):
        self.assertEqual(_detect(_Probe(["mysqldump"])), ("mariadb", "mysqldump"))

    def test_a_container_without_either_tool_is_no_database(self):
        self.assertIsNone(_detect(_Probe([])))

    def test_the_probe_stops_at_the_first_tool_it_finds(self):
        probe = _Probe(["pg_dumpall", "mariadb-dump"])
        _detect(probe)
        self.assertEqual(probe.calls, [("c1", "pg_dumpall")])

    def test_the_image_name_does_not_decide_the_engine(self):
        """The trap the old substring test fell into, from both directions."""
        probe = _Probe(["pg_dumpall"], image="svc-db-mariadb-mgr-01:5000/pg_custom")
        self.assertEqual(_detect(probe), ("postgres", "pg_dumpall"))

        probe = _Probe(["mariadb-dump"], image="discourse-database:17")
        self.assertEqual(_detect(probe), ("mariadb", "mariadb-dump"))


class TestProbeCache(unittest.TestCase):
    def test_replicas_of_one_image_are_probed_once(self):
        probe = _Probe(["pg_dumpall"])
        dumps_mod._ENGINE_BY_IMAGE.clear()
        with (
            patch.object(dumps_mod, "has_tool", probe.has_tool),
            patch.object(dumps_mod, "image_id", probe.image_id),
        ):
            first = dumps_mod.container_engine("replica-1")
            second = dumps_mod.container_engine("replica-2")
        self.assertEqual(first, second)
        self.assertEqual(len(probe.calls), 1)

    def test_a_second_image_is_probed_separately(self):
        probe = _Probe(["pg_dumpall"], image={"pg": "sha256:aaa", "app": "sha256:bbb"})
        dumps_mod._ENGINE_BY_IMAGE.clear()
        with (
            patch.object(dumps_mod, "has_tool", probe.has_tool),
            patch.object(dumps_mod, "image_id", probe.image_id),
        ):
            self.assertEqual(
                dumps_mod.container_engine("pg"), ("postgres", "pg_dumpall")
            )
            probe.available = set()
            self.assertIsNone(dumps_mod.container_engine("app"))


class TestBackupDispatch(unittest.TestCase):
    def test_the_probed_tool_reaches_the_dump(self):
        probe = _Probe(["mysqldump"])
        seen = {}

        def _fake_backup_database(**kwargs):
            seen.update(kwargs)
            return True

        dumps_mod._ENGINE_BY_IMAGE.clear()
        with (
            patch.object(dumps_mod, "has_tool", probe.has_tool),
            patch.object(dumps_mod, "image_id", probe.image_id),
            patch.object(dumps_mod, "backup_database", _fake_backup_database),
        ):
            is_db, dumped = dumps_mod.backup_mariadb_or_postgres(
                container="c1",
                volume_dir="/tmp",
                databases_df=_df([("c1", "appdb", "u", "p")]),
                database_containers=["c1"],
            )

        self.assertTrue(is_db)
        self.assertTrue(dumped)
        self.assertEqual(seen["db_type"], "mariadb")
        self.assertEqual(seen["dump_tool"], "mysqldump")

    def test_a_non_database_container_is_left_to_the_file_backup(self):
        probe = _Probe([])
        dumps_mod._ENGINE_BY_IMAGE.clear()
        with (
            patch.object(dumps_mod, "has_tool", probe.has_tool),
            patch.object(dumps_mod, "image_id", probe.image_id),
        ):
            self.assertEqual(
                dumps_mod.backup_mariadb_or_postgres(
                    container="c1",
                    volume_dir="/tmp",
                    databases_df=_df([]),
                    database_containers=[],
                ),
                (False, False),
            )


if __name__ == "__main__":
    unittest.main()
