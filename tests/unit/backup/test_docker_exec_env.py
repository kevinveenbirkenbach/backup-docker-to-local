"""How a secret reaches the command running inside the container."""

from __future__ import annotations

import unittest

from baudolo.backup.db import fallback_pg_dumpall
from baudolo.backup.docker import docker_exec_argv


class TestForwardEnv(unittest.TestCase):
    def test_nothing_is_added_when_no_variable_is_named(self) -> None:
        self.assertEqual(
            docker_exec_argv("c1", ["true"]),
            ["docker", "exec", "c1", "true"],
        )

    def test_a_named_variable_is_forwarded_without_its_value(self) -> None:
        """-e NAME=value would publish the secret in the host's process list."""
        argv = docker_exec_argv("c1", ["true"], forward_env=["PGPASSWORD"])
        self.assertEqual(argv, ["docker", "exec", "-e", "PGPASSWORD", "c1", "true"])

    def test_the_flag_precedes_the_container(self) -> None:
        """docker reads options before the container name, arguments after it."""
        argv = docker_exec_argv(
            "c1", ["pg_dump", "-U", "u"], interactive=True, forward_env=["PGPASSWORD"]
        )
        self.assertLess(argv.index("-e"), argv.index("c1"))
        self.assertLess(argv.index("-i"), argv.index("c1"))
        self.assertGreater(argv.index("pg_dump"), argv.index("c1"))

    def test_several_variables_each_get_their_own_flag(self) -> None:
        argv = docker_exec_argv("c1", ["true"], forward_env=["A", "B"])
        self.assertEqual(argv[:6], ["docker", "exec", "-e", "A", "-e", "B"])


class TestPostgresDumpCarriesThePassword(unittest.TestCase):
    def test_the_cluster_dump_forwards_pgpassword(self) -> None:
        seen: dict = {}

        def fake(command, out_file, *, env=None):
            seen["command"] = command
            seen["env"] = env

        import baudolo.backup.db as db

        original = db.execute_to_file
        db.execute_to_file = fake
        try:
            fallback_pg_dumpall("pg", "user", "secret", "/tmp/out.sql")
        finally:
            db.execute_to_file = original

        self.assertIn("-e", seen["command"])
        self.assertEqual(seen["command"][seen["command"].index("-e") + 1], "PGPASSWORD")
        self.assertEqual(seen["env"], {"PGPASSWORD": "secret"})
        self.assertNotIn("secret", seen["command"])


if __name__ == "__main__":
    unittest.main()
