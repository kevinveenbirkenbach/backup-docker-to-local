import unittest
from unittest.mock import patch

from baudolo.backup import docker as docker_mod
from baudolo.backup.shell import BackupException


class TestImageId(unittest.TestCase):
    def test_the_id_is_returned_without_surrounding_whitespace(self) -> None:
        with patch.object(
            docker_mod, "execute_shell_command", return_value=["sha256:abc \n"]
        ):
            self.assertEqual(docker_mod.image_id("c1"), "sha256:abc")


class TestHasTool(unittest.TestCase):
    def test_a_tool_that_runs_is_present(self) -> None:
        with patch.object(docker_mod, "execute_shell_command", return_value=[]):
            self.assertTrue(docker_mod.has_tool("c1", "pg_dumpall"))

    def test_a_tool_that_exits_non_zero_is_absent(self) -> None:
        with patch.object(
            docker_mod, "execute_shell_command", side_effect=BackupException("127")
        ):
            self.assertFalse(docker_mod.has_tool("c1", "mariadb-dump"))

    def test_the_probe_needs_no_shell_in_the_image(self) -> None:
        """A distroless database ships no shell; `sh -c` would deny every tool."""
        captured = []

        def _capture(cmd):
            captured.append(cmd)
            return []

        with patch.object(docker_mod, "execute_shell_command", side_effect=_capture):
            docker_mod.has_tool("c1", "pg_dumpall")

        self.assertEqual(captured, ["docker exec c1 pg_dumpall --version"])


if __name__ == "__main__":
    unittest.main()
