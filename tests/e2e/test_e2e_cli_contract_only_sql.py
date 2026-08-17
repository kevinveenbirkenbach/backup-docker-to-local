import unittest

from .helpers import run

WITHDRAWN_FLAGS = ["--dump-only", "--dump-only-sql", "--everything"]


class TestE2ECLIContractOnlySql(unittest.TestCase):
    def test_help_mentions_the_flag(self) -> None:
        cp = run(["baudolo", "--help"], capture=True, check=True)
        out = (cp.stdout or "") + "\n" + (cp.stderr or "")
        self.assertIn(
            "--only-sql",
            out,
            f"Expected '--only-sql' to appear in --help output. Output:\n{out}",
        )

    def test_a_withdrawn_flag_is_rejected(self) -> None:
        for flag in WITHDRAWN_FLAGS:
            with self.subTest(flag=flag):
                cp = run(["baudolo", flag], capture=True, check=False)
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
