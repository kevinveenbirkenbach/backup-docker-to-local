import unittest
from unittest.mock import patch

from baudolo.backup import docker as docker_mod
from baudolo.backup.shell import BackupException


class TestIsSwarmTask(unittest.TestCase):
    @patch.object(docker_mod, "execute_shell_command", return_value=["task-id-123"])
    def test_true_when_task_label_present(self, _mock) -> None:
        self.assertTrue(docker_mod.is_swarm_task("c1"))

    @patch.object(docker_mod, "execute_shell_command", return_value=[""])
    def test_false_when_label_empty(self, _mock) -> None:
        self.assertFalse(docker_mod.is_swarm_task("c1"))

    @patch.object(docker_mod, "execute_shell_command", return_value=[])
    def test_false_when_no_output(self, _mock) -> None:
        self.assertFalse(docker_mod.is_swarm_task("c1"))

    @patch.object(
        docker_mod,
        "execute_shell_command",
        side_effect=BackupException("gone"),
    )
    def test_vanished_container_counts_as_not_stoppable(self, _mock) -> None:
        # A container removed between listing and inspect must not abort the
        # whole backup run; treating it as a swarm task keeps it out of every
        # stop/start and image-inspect path.
        self.assertTrue(docker_mod.is_swarm_task("gone-container"))


class TestFilterStoppable(unittest.TestCase):
    @patch.object(docker_mod, "is_swarm_task", side_effect=[False, True, False])
    def test_mixed_list_keeps_order_and_drops_tasks(self, _mock) -> None:
        result = docker_mod.filter_stoppable(["plain-1", "swarm-task", "plain-2"])
        self.assertEqual(result, ["plain-1", "plain-2"])


if __name__ == "__main__":
    unittest.main()
