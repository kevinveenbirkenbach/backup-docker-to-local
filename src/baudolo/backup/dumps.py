"""Database dumps taken before a volume's files are copied."""

from __future__ import annotations

import sys

import pandas
from pandas.errors import EmptyDataError

from .db import backup_database
from .docker import has_image


def backup_mariadb_or_postgres(
    *,
    container: str,
    volume_dir: str,
    databases_df: "pandas.DataFrame",
    database_containers: list[str],
) -> tuple[bool, bool]:
    """
    Returns (is_db_container, dumped_any)
    """
    for img in ["mariadb", "postgres"]:
        if has_image(container, img):
            dumped = backup_database(
                container=container,
                volume_dir=volume_dir,
                db_type=img,
                databases_df=databases_df,
                database_containers=database_containers,
            )
            return True, dumped
    return False, False


def _empty_databases_df() -> "pandas.DataFrame":
    """
    Create an empty DataFrame with the expected schema for databases.csv.

    This allows the backup to continue without DB dumps when the CSV is missing
    or empty (pandas EmptyDataError).
    """
    return pandas.DataFrame(columns=["instance", "database", "username", "password"])


def load_databases_df(csv_path: str) -> "pandas.DataFrame":
    """
    Load databases.csv robustly.

    - Missing file     -> warn, continue with empty df
    - Empty file       -> warn, continue with empty df
    - Valid CSV        -> return dataframe
    """
    try:
        return pandas.read_csv(csv_path, sep=";", keep_default_na=False, dtype=str)
    except FileNotFoundError:
        print(
            f"WARNING: databases.csv not found: {csv_path}. Continuing without database dumps.",
            file=sys.stderr,
            flush=True,
        )
        return _empty_databases_df()
    except EmptyDataError:
        print(
            f"WARNING: databases.csv exists but is empty: {csv_path}. Continuing without database dumps.",
            file=sys.stderr,
            flush=True,
        )
        return _empty_databases_df()


def backup_dumps_for_volume(
    *,
    containers: list[str],
    vol_dir: str,
    databases_df: "pandas.DataFrame",
    database_containers: list[str],
) -> tuple[bool, bool]:
    """
    Returns (found_db_container, dumped_any)
    """
    found_db = False
    dumped_any = False

    for c in containers:
        is_db, dumped = backup_mariadb_or_postgres(
            container=c,
            volume_dir=vol_dir,
            databases_df=databases_df,
            database_containers=database_containers,
        )
        if is_db:
            found_db = True
        if dumped:
            dumped_any = True

    return found_db, dumped_any
