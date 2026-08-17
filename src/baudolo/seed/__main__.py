from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from pandas.errors import EmptyDataError

from baudolo.databases import COLUMNS, DELIMITER, validate_database


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=list(COLUMNS))


def check_and_add_entry(
    file_path: str,
    instance: str,
    database: str | None,
    username: str,
    password: str,
) -> None:
    """
    Add or update an entry in databases.csv.

    The function enforces strict validation:
    - database MUST be set
    - database MUST be '*' or a valid database name
    """
    database = validate_database(database, instance=instance)

    if Path(file_path).exists():
        try:
            df = pd.read_csv(
                file_path,
                sep=DELIMITER,
                dtype=str,
                keep_default_na=False,
            )
        except EmptyDataError:
            print(
                f"WARNING: databases.csv exists but is empty: {file_path}. Creating header columns.",
                file=sys.stderr,
            )
            df = _empty_df()
    else:
        df = _empty_df()
    mask = (df["instance"] == instance) & (df["database"] == database)

    if mask.any():
        print("Updating existing entry.")
        df.loc[mask, ["username", "password"]] = [username, password]
    else:
        print("Adding new entry.")
        new_entry = pd.DataFrame(
            [[instance, database, username, password]],
            columns=list(COLUMNS),
        )
        df = pd.concat([df, new_entry], ignore_index=True)

    df.to_csv(file_path, sep=DELIMITER, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed or update databases.csv for backup configuration."
    )
    parser.add_argument("file", help="Path to databases.csv")
    parser.add_argument("instance", help="Instance name (e.g. bigbluebutton)")
    parser.add_argument(
        "database",
        help="Database name or '*' to dump all databases",
    )
    parser.add_argument("username", help="Database username")
    parser.add_argument("password", help="Database password")

    args = parser.parse_args()

    try:
        check_and_add_entry(
            file_path=args.file,
            instance=args.instance,
            database=args.database,
            username=args.username,
            password=args.password,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary: any failure becomes exit 1
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
