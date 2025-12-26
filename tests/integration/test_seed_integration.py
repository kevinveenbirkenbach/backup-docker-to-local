import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def run_seed(csv_path: Path, instance: str, database: str, username: str, password: str = "") -> subprocess.CompletedProcess:
    # Run the real CLI module (integration-style).
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "baudolo.seed",
            str(csv_path),
            instance,
            database,
            username,
            password,
        ],
        text=True,
        capture_output=True,
        check=True,
    )


def read_csv_semicolon(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        return list(reader)


class TestSeedIntegration(unittest.TestCase):
    def test_creates_file_and_adds_entry_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "databases.csv"
            self.assertFalse(p.exists())

            cp = run_seed(p, "docker.test", "appdb", "alice", "secret")

            self.assertEqual(cp.returncode, 0, cp.stderr)
            self.assertTrue(p.exists())

            rows = read_csv_semicolon(p)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["instance"], "docker.test")
            self.assertEqual(rows[0]["database"], "appdb")
            self.assertEqual(rows[0]["username"], "alice")
            self.assertEqual(rows[0]["password"], "secret")

    def test_replaces_existing_entry_same_keys(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "databases.csv"

            # First add
            run_seed(p, "docker.test", "appdb", "alice", "oldpw")
            rows = read_csv_semicolon(p)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["password"], "oldpw")

            # Replace (same instance+database+username)
            run_seed(p, "docker.test", "appdb", "alice", "newpw")
            rows = read_csv_semicolon(p)

            self.assertEqual(len(rows), 1, "Expected replacement, not a duplicate row")
            self.assertEqual(rows[0]["instance"], "docker.test")
            self.assertEqual(rows[0]["database"], "appdb")
            self.assertEqual(rows[0]["username"], "alice")
            self.assertEqual(rows[0]["password"], "newpw")

    def test_database_empty_string_matches_existing_empty_database(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "databases.csv"

            # Add with empty database
            run_seed(p, "docker.test", "", "alice", "pw1")
            rows = read_csv_semicolon(p)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["database"], "")

            # Replace with empty database again
            run_seed(p, "docker.test", "", "alice", "pw2")
            rows = read_csv_semicolon(p)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["database"], "")
            self.assertEqual(rows[0]["password"], "pw2")
