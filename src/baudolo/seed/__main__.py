#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
import pandas as pd
from typing import Optional


DB_NAME_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_-]*$")

def _validate_database_value(value: Optional[str], *, instance: str) -> str:
    v = (value or "").strip()
    if v == "":
        raise ValueError(
            f"Invalid databases.csv entry for instance '{instance}': "
            "column 'database' must be '*' or a concrete database name (not empty)."
        )
    if v == "*":
        return "*"
    if v.lower() == "nan":
        raise ValueError(
            f"Invalid databases.csv entry for instance '{instance}': database must not be 'nan'."
        )
    if not DB_NAME_RE.match(v):
        raise ValueError(
            f"Invalid databases.csv entry for instance '{instance}': "
            f"invalid database name '{v}'. Allowed: letters, numbers, '_' and '-'."
        )
    return v

def check_and_add_entry(
    file_path: str,
    instance: str,
    database: Optional[str],
    username: str,
    password: str,
) -> None:
    """
    Add or update an entry in databases.csv.

    The function enforces strict validation:
    - database MUST be set
    - database MUST be '*' or a valid database name
    """
    database = _validate_database_value(database, instance=instance)

    if os.path.exists(file_path):
        df = pd.read_csv(
            file_path,
            sep=";",
            dtype=str,
            keep_default_na=False,
        )
    else:
        df = pd.DataFrame(
            columns=["instance", "database", "username", "password"]
        )

    mask = (df["instance"] == instance) & (df["database"] == database)

    if mask.any():
        print("Updating existing entry.")
        df.loc[mask, ["username", "password"]] = [username, password]
    else:
        print("Adding new entry.")
        new_entry = pd.DataFrame(
            [[instance, database, username, password]],
            columns=["instance", "database", "username", "password"],
        )
        df = pd.concat([df, new_entry], ignore_index=True)

    df.to_csv(file_path, sep=";", index=False)


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
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
