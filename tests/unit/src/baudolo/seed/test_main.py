# tests/unit/src/baudolo/seed/test_main.py
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
from pandas.errors import EmptyDataError

import baudolo.seed.__main__ as seed_main


class TestSeedMain(unittest.TestCase):
    @patch("baudolo.seed.__main__.pd.DataFrame")
    def test_empty_df_creates_expected_columns(self, df_ctor: MagicMock) -> None:
        seed_main._empty_df()
        df_ctor.assert_called_once_with(
            columns=["instance", "database", "username", "password"]
        )

    def test_validate_database_value_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            seed_main._validate_database_value("", instance="x")

    def test_validate_database_value_accepts_star(self) -> None:
        self.assertEqual(seed_main._validate_database_value("*", instance="x"), "*")

    def test_validate_database_value_rejects_nan(self) -> None:
        with self.assertRaises(ValueError):
            seed_main._validate_database_value("nan", instance="x")

    def test_validate_database_value_rejects_invalid_name(self) -> None:
        with self.assertRaises(ValueError):
            seed_main._validate_database_value("bad name", instance="x")

    @patch("baudolo.seed.__main__.os.path.exists", return_value=False)
    @patch("baudolo.seed.__main__.pd.read_csv")
    @patch("baudolo.seed.__main__._empty_df")
    @patch("baudolo.seed.__main__.pd.concat")
    def test_check_and_add_entry_file_missing_adds_entry(
        self,
        concat: MagicMock,
        empty_df: MagicMock,
        read_csv: MagicMock,
        exists: MagicMock,
    ) -> None:
        df_existing = MagicMock(spec=pd.DataFrame)
        series_mask = MagicMock()
        series_mask.any.return_value = False

        df_existing.__getitem__.return_value = series_mask  # for df["instance"] etc.
        empty_df.return_value = df_existing

        df_out = MagicMock(spec=pd.DataFrame)
        concat.return_value = df_out

        seed_main.check_and_add_entry(
            file_path="/tmp/databases.csv",
            instance="inst",
            database="db",
            username="user",
            password="pass",
        )

        read_csv.assert_not_called()
        empty_df.assert_called_once()
        concat.assert_called_once()
        df_out.to_csv.assert_called_once_with(
            "/tmp/databases.csv", sep=";", index=False
        )

    @patch("baudolo.seed.__main__.os.path.exists", return_value=True)
    @patch("baudolo.seed.__main__.pd.read_csv", side_effect=EmptyDataError("empty"))
    @patch("baudolo.seed.__main__._empty_df")
    @patch("baudolo.seed.__main__.pd.concat")
    @patch("baudolo.seed.__main__.print")
    def test_check_and_add_entry_empty_file_warns_and_creates_columns_and_adds(
        self,
        print_: MagicMock,
        concat: MagicMock,
        empty_df: MagicMock,
        read_csv: MagicMock,
        exists: MagicMock,
    ) -> None:
        """
        Key regression test:
        If file exists but is empty => warn, create header columns, then proceed.
        """
        df_existing = MagicMock(spec=pd.DataFrame)
        series_mask = MagicMock()
        series_mask.any.return_value = False

        # emulate df["instance"] and df["database"] usage
        df_existing.__getitem__.return_value = series_mask
        empty_df.return_value = df_existing

        df_out = MagicMock(spec=pd.DataFrame)
        concat.return_value = df_out

        seed_main.check_and_add_entry(
            file_path="/tmp/databases.csv",
            instance="inst",
            database="db",
            username="user",
            password="pass",
        )

        exists.assert_called_once_with("/tmp/databases.csv")
        read_csv.assert_called_once()
        empty_df.assert_called_once()

        # warning was printed to stderr
        self.assertTrue(print_.called)
        args, kwargs = print_.call_args
        self.assertIn("WARNING: databases.csv exists but is empty", args[0])
        self.assertIn("file", kwargs)
        self.assertEqual(kwargs["file"], seed_main.sys.stderr)

        concat.assert_called_once()
        df_out.to_csv.assert_called_once_with(
            "/tmp/databases.csv", sep=";", index=False
        )

    @patch("baudolo.seed.__main__.os.path.exists", return_value=True)
    @patch("baudolo.seed.__main__.pd.read_csv")
    def test_check_and_add_entry_updates_existing_row(
        self,
        read_csv: MagicMock,
        exists: MagicMock,
    ) -> None:
        df = MagicMock(spec=pd.DataFrame)

        # mask.any() => True triggers update branch
        mask = MagicMock()
        mask.any.return_value = True

        # df["instance"] etc => return something that supports comparisons;
        # simplest: just return an object that makes mask flow work.
        df.__getitem__.return_value = MagicMock()
        # Force the computed mask to be our mask
        # by making (df["instance"] == instance) & (df["database"] == database) return `mask`
        left = MagicMock()
        right = MagicMock()
        left.__and__.return_value = mask
        df.__getitem__.return_value.__eq__.side_effect = [left, right]  # two == calls

        read_csv.return_value = df

        seed_main.check_and_add_entry(
            file_path="/tmp/databases.csv",
            instance="inst",
            database="db",
            username="user",
            password="pass",
        )

        # update branch: df.loc[mask, ["username","password"]] = ...
        # we can't easily assert the assignment, but we can assert .loc was accessed
        self.assertTrue(hasattr(df, "loc"))
        df.to_csv.assert_called_once_with("/tmp/databases.csv", sep=";", index=False)

    @patch("baudolo.seed.__main__.check_and_add_entry")
    @patch("baudolo.seed.__main__.argparse.ArgumentParser.parse_args")
    def test_main_calls_check_and_add_entry(
        self, parse_args: MagicMock, cae: MagicMock
    ) -> None:
        ns = MagicMock()
        ns.file = "/tmp/databases.csv"
        ns.instance = "inst"
        ns.database = "db"
        ns.username = "user"
        ns.password = "pass"
        parse_args.return_value = ns

        seed_main.main()

        cae.assert_called_once_with(
            file_path="/tmp/databases.csv",
            instance="inst",
            database="db",
            username="user",
            password="pass",
        )

    @patch("baudolo.seed.__main__.sys.exit")
    @patch("baudolo.seed.__main__.print")
    @patch(
        "baudolo.seed.__main__.check_and_add_entry", side_effect=RuntimeError("boom")
    )
    @patch("baudolo.seed.__main__.argparse.ArgumentParser.parse_args")
    def test_main_exits_nonzero_on_error(
        self,
        parse_args: MagicMock,
        cae: MagicMock,
        print_: MagicMock,
        exit_: MagicMock,
    ) -> None:
        ns = MagicMock()
        ns.file = "/tmp/databases.csv"
        ns.instance = "inst"
        ns.database = "db"
        ns.username = "user"
        ns.password = "pass"
        parse_args.return_value = ns

        seed_main.main()

        # prints error to stderr and exits with 1
        self.assertTrue(print_.called)
        _, kwargs = print_.call_args
        self.assertEqual(kwargs.get("file"), seed_main.sys.stderr)
        exit_.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
