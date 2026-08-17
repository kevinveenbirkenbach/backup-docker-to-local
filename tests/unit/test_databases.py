"""Contract of databases.csv: the seed writes it, the backup and a restore read it."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from baudolo.databases import (
    CLUSTER_ROW,
    COLUMNS,
    DELIMITER,
    DatabasesCsvError,
    Row,
    read_rows,
    validate_database,
)

HEADER = DELIMITER.join(COLUMNS)


def _csv(*lines: str) -> str:
    path = Path(tempfile.mkdtemp()) / "databases.csv"
    path.write_text("\n".join((HEADER, *lines)) + "\n", encoding="utf-8")
    return str(path)


class TestValidateDatabase(unittest.TestCase):
    def test_a_concrete_name_passes(self) -> None:
        self.assertEqual(validate_database("app_db-1", instance="x"), "app_db-1")

    def test_the_cluster_marker_passes(self) -> None:
        self.assertEqual(validate_database(CLUSTER_ROW, instance="x"), CLUSTER_ROW)

    def test_an_empty_column_is_rejected(self) -> None:
        with self.assertRaises(DatabasesCsvError):
            validate_database("", instance="x")

    def test_the_string_nan_is_rejected(self) -> None:
        """pandas used to hand back NaN, which wrote a nan.backup.sql."""
        with self.assertRaises(DatabasesCsvError):
            validate_database("nan", instance="x")

    def test_a_name_that_could_reach_a_shell_is_rejected(self) -> None:
        for hostile in ("bad name", "a;rm -rf /", "$(id)", "a`id`", "a/b"):
            with self.subTest(name=hostile), self.assertRaises(DatabasesCsvError):
                validate_database(hostile, instance="x")

    def test_the_error_is_a_value_error(self) -> None:
        """Callers predating the shared module catch ValueError."""
        with self.assertRaises(ValueError):
            validate_database("", instance="x")


class TestReadRows(unittest.TestCase):
    def test_the_header_is_skipped(self) -> None:
        rows = read_rows(_csv(f"pg{DELIMITER}app{DELIMITER}u{DELIMITER}p"))
        self.assertEqual(rows, [Row("pg", "app", "u", "p")])

    def test_a_blank_row_is_dropped(self) -> None:
        rows = read_rows(_csv("", f"pg{DELIMITER}app{DELIMITER}u{DELIMITER}p", ""))
        self.assertEqual(len(rows), 1)

    def test_a_short_row_is_refused(self) -> None:
        with self.assertRaises(DatabasesCsvError):
            read_rows(_csv(f"pg{DELIMITER}app{DELIMITER}u"))

    def test_values_arrive_verbatim(self) -> None:
        """A password may legitimately begin or end with a space."""
        rows = read_rows(_csv(f"pg{DELIMITER}app{DELIMITER}u{DELIMITER} pw "))
        self.assertEqual(rows[0].password, " pw ")

    def test_a_cluster_row_knows_itself(self) -> None:
        rows = read_rows(
            _csv(
                f"pg{DELIMITER}{CLUSTER_ROW}{DELIMITER}postgres{DELIMITER}p",
                f"pg{DELIMITER}app{DELIMITER}u{DELIMITER}p",
            )
        )
        self.assertEqual([row.is_cluster for row in rows], [True, False])


if __name__ == "__main__":
    unittest.main()
