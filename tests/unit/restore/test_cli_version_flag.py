import unittest
from unittest.mock import patch

from baudolo.restore import __main__ as cli

ENGINES = {
    "postgres": ("restore_postgres_sql", ["--db-name", "app"]),
    "mariadb": ("restore_mariadb_sql", ["--db-name", "app"]),
    "cluster": ("restore_cluster_sql", ["--instance", "central", "--db-user", "root"]),
}


class TestVersionFlagReachesEveryEngine(unittest.TestCase):
    def call(self, engine: str, extra: list) -> dict:
        target, required = ENGINES[engine]
        argv = [
            engine,
            "app_vol",
            "hash",
            "20260817000000",
            "--container",
            "db",
            "--db-password",
            "pw",
            *required,
            *extra,
        ]
        with patch.object(cli, target) as restore:
            self.assertEqual(cli.main(argv), 0)
        return restore.call_args.kwargs

    def test_the_gate_is_on_by_default(self) -> None:
        for engine in ENGINES:
            with self.subTest(engine=engine):
                self.assertTrue(self.call(engine, [])["check_version"])

    def test_the_flag_turns_it_off(self) -> None:
        for engine in ENGINES:
            with self.subTest(engine=engine):
                kwargs = self.call(engine, ["--no-version-check"])
                self.assertFalse(kwargs["check_version"])

    def test_empty_stays_independent_of_the_gate(self) -> None:
        for engine in ENGINES:
            with self.subTest(engine=engine):
                kwargs = self.call(engine, ["--empty"])
                self.assertTrue(kwargs["empty"])
                self.assertTrue(kwargs["check_version"])


if __name__ == "__main__":
    unittest.main()
