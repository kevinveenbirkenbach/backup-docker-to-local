import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def run_seed(
    csv_path: Path, instance: str, database: str, username: str, password: str
) -> subprocess.CompletedProcess:
    """
    Run the real CLI module (E2E-style) using subprocess.

    Seed contract (current):
    - database must be "*" or a valid name (non-empty, matches allowed charset)
    - password is required
    - entry is keyed by (instance, database); username/password get updated
    """
    cp = subprocess.run(
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
        check=False,
    )
    if cp.returncode != 0:
        raise AssertionError(
            "seed command failed unexpectedly.\n"
            f"returncode: {cp.returncode}\n"
            f"stdout:\n{cp.stdout}\n"
            f"stderr:\n{cp.stderr}\n"
        )
    return cp


def run_seed_expect_fail(
    csv_path: Path, instance: str, database: str, username: str, password: str
) -> subprocess.CompletedProcess:
    """
    Same as run_seed, but expects non-zero exit. Returns CompletedProcess for inspection.
    """
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
        check=False,
    )


def read_csv_semicolon(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        return list(reader)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestSeedIntegration(unittest.TestCase):
    def test_creates_file_and_adds_entry_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "databases.csv"
            self.assertFalse(p.exists())

            cp = run_seed(p, "docker.test", "appdb", "alice", "secret")

            self.assertEqual(cp.returncode, 0)
            self.assertTrue(p.exists())

            rows = read_csv_semicolon(p)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["instance"], "docker.test")
            self.assertEqual(rows[0]["database"], "appdb")
            self.assertEqual(rows[0]["username"], "alice")
            self.assertEqual(rows[0]["password"], "secret")

    def test_replaces_existing_entry_same_instance_and_database_updates_username_and_password(
        self,
    ) -> None:
        """
        Replacement semantics:
        - Key is (instance, database)
        - username/password are updated in-place
        """
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "databases.csv"

            run_seed(p, "docker.test", "appdb", "alice", "oldpw")
            rows = read_csv_semicolon(p)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["username"], "alice")
            self.assertEqual(rows[0]["password"], "oldpw")

            run_seed(p, "docker.test", "appdb", "bob", "newpw")
            rows = read_csv_semicolon(p)

            self.assertEqual(len(rows), 1, "Expected replacement, not a duplicate row")
            self.assertEqual(rows[0]["instance"], "docker.test")
            self.assertEqual(rows[0]["database"], "appdb")
            self.assertEqual(rows[0]["username"], "bob")
            self.assertEqual(rows[0]["password"], "newpw")

    def test_allows_star_database_for_dump_all(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "databases.csv"

            cp = run_seed(p, "bigbluebutton", "*", "postgres", "pw")
            self.assertEqual(cp.returncode, 0)

            rows = read_csv_semicolon(p)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["instance"], "bigbluebutton")
            self.assertEqual(rows[0]["database"], "*")
            self.assertEqual(rows[0]["username"], "postgres")
            self.assertEqual(rows[0]["password"], "pw")

    def test_replaces_existing_star_entry(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "databases.csv"

            run_seed(p, "bigbluebutton", "*", "postgres", "pw1")
            run_seed(p, "bigbluebutton", "*", "postgres", "pw2")

            rows = read_csv_semicolon(p)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["database"], "*")
            self.assertEqual(rows[0]["password"], "pw2")

    def test_rejects_empty_database_value(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "databases.csv"

            cp = run_seed_expect_fail(p, "docker.test", "", "alice", "pw")
            self.assertNotEqual(cp.returncode, 0)

            combined = ((cp.stdout or "") + "\n" + (cp.stderr or "")).lower()
            self.assertIn("error:", combined)
            self.assertIn("database", combined)
            self.assertIn("not empty", combined)

            self.assertFalse(p.exists(), "Should not create file on invalid input")

    def test_rejects_invalid_database_name_characters(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "databases.csv"

            cp = run_seed_expect_fail(p, "docker.test", "app db", "alice", "pw")
            self.assertNotEqual(cp.returncode, 0)

            combined = ((cp.stdout or "") + "\n" + (cp.stderr or "")).lower()
            self.assertIn("error:", combined)
            self.assertIn("invalid database name", combined)

            self.assertFalse(p.exists(), "Should not create file on invalid input")

    def test_rejects_nan_database_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "databases.csv"

            cp = run_seed_expect_fail(p, "docker.test", "nan", "alice", "pw")
            self.assertNotEqual(cp.returncode, 0)

            combined = ((cp.stdout or "") + "\n" + (cp.stderr or "")).lower()
            self.assertIn("error:", combined)
            self.assertIn("must not be 'nan'", combined)

            self.assertFalse(p.exists(), "Should not create file on invalid input")

    def test_accepts_hyphen_and_underscore_database_names(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "databases.csv"

            run_seed(p, "docker.test", "my_db-1", "alice", "pw")

            rows = read_csv_semicolon(p)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["database"], "my_db-1")

    def test_file_is_semicolon_delimited_and_has_header(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "databases.csv"

            run_seed(p, "docker.test", "appdb", "alice", "pw")

            txt = read_text(p)
            self.assertTrue(
                txt.startswith("instance;database;username;password"),
                f"Unexpected header / delimiter in file:\n{txt}",
            )
            self.assertIn(";", txt)


if __name__ == "__main__":
    unittest.main()
