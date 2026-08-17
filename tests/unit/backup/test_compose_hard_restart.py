from __future__ import annotations

import unittest
from unittest.mock import patch

from . import BASE_ARGV


class HardRestartArgTests(unittest.TestCase):
    """The hard-restart list defaults to empty (no compose down/up); callers
    opt in per dir, e.g. compose hosts pass 'mailu' while swarm hosts, where
    the dir is a stack whose overlay network collides with compose up, pass
    nothing."""

    def _parse(self, extra: list[str]):
        import sys

        from baudolo.backup import cli

        argv = [
            *BASE_ARGV,
            "--database-containers",
            "postgres",
            "--images-no-stop-required",
            "redis",
            *extra,
        ]
        with patch.object(sys, "argv", argv):
            return cli.parse_args()

    def test_default_is_empty(self) -> None:
        args = self._parse([])
        self.assertEqual(args.hard_restart_projects, [])

    def test_empty_flag_stays_empty(self) -> None:
        args = self._parse(["--hard-restart-projects"])
        self.assertEqual(args.hard_restart_projects, [])

    def test_explicit_names_preserved(self) -> None:
        args = self._parse(["--hard-restart-projects", "mailu", "foo"])
        self.assertEqual(args.hard_restart_projects, ["mailu", "foo"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
