import unittest

from .helpers import run


class TestE2ECLIContractDumpOnlySql(unittest.TestCase):
    def test_help_mentions_new_flag(self) -> None:
        cp = run(["baudolo", "--help"], capture=True, check=True)
        out = (cp.stdout or "") + "\n" + (cp.stderr or "")
        self.assertIn(
            "--dump-only-sql",
            out,
            f"Expected '--dump-only-sql' to appear in --help output. Output:\n{out}",
        )

    def test_help_does_not_mention_old_flag(self) -> None:
        cp = run(["baudolo", "--help"], capture=True, check=True)
        out = (cp.stdout or "") + "\n" + (cp.stderr or "")
        self.assertNotIn(
            "--dump-only",
            out,
            f"Did not expect legacy '--dump-only' to appear in --help output. Output:\n{out}",
        )

    def test_old_flag_is_rejected(self) -> None:
        cp = run(["baudolo", "--dump-only"], capture=True, check=False)
        self.assertEqual(
            cp.returncode,
            2,
            f"Expected exitcode 2 for unknown args, got {cp.returncode}\n"
            f"STDOUT={cp.stdout}\nSTDERR={cp.stderr}",
        )
        err = (cp.stderr or "") + "\n" + (cp.stdout or "")
        # Argparse typically prints "unrecognized arguments"
        self.assertTrue(
            ("unrecognized arguments" in err) or ("usage:" in err.lower()),
            f"Expected argparse-style error output. Output:\n{err}",
        )
