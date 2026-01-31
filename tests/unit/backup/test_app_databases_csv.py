import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr

import pandas as pd

# Adjust if your package name/import path differs.
from baudolo.backup.app import _load_databases_df


EXPECTED_COLUMNS = ["instance", "database", "username", "password"]


class TestLoadDatabasesDf(unittest.TestCase):
    def test_missing_csv_is_handled_with_warning_and_empty_df(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            missing_path = os.path.join(td, "does-not-exist.csv")

            buf = io.StringIO()
            with redirect_stderr(buf):
                df = _load_databases_df(missing_path)

            stderr = buf.getvalue()
            self.assertIn("WARNING:", stderr)
            self.assertIn("databases.csv not found", stderr)

            self.assertIsInstance(df, pd.DataFrame)
            self.assertListEqual(list(df.columns), EXPECTED_COLUMNS)
            self.assertTrue(df.empty)

    def test_empty_csv_is_handled_with_warning_and_empty_df(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            empty_path = os.path.join(td, "databases.csv")
            # Create an empty file (0 bytes)
            with open(empty_path, "w", encoding="utf-8") as f:
                f.write("")

            buf = io.StringIO()
            with redirect_stderr(buf):
                df = _load_databases_df(empty_path)

            stderr = buf.getvalue()
            self.assertIn("WARNING:", stderr)
            self.assertIn("exists but is empty", stderr)

            self.assertIsInstance(df, pd.DataFrame)
            self.assertListEqual(list(df.columns), EXPECTED_COLUMNS)
            self.assertTrue(df.empty)

    def test_valid_csv_loads_without_warning(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            csv_path = os.path.join(td, "databases.csv")

            content = "instance;database;username;password\nmyapp;*;dbuser;secret\n"
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write(content)

            buf = io.StringIO()
            with redirect_stderr(buf):
                df = _load_databases_df(csv_path)

            stderr = buf.getvalue()
            self.assertEqual(stderr, "")  # no warning expected

            self.assertIsInstance(df, pd.DataFrame)
            self.assertListEqual(list(df.columns), EXPECTED_COLUMNS)
            self.assertEqual(len(df), 1)
            self.assertEqual(df.loc[0, "instance"], "myapp")
            self.assertEqual(df.loc[0, "database"], "*")
            self.assertEqual(df.loc[0, "username"], "dbuser")
            self.assertEqual(df.loc[0, "password"], "secret")


if __name__ == "__main__":
    unittest.main()
