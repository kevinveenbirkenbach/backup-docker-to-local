"""Database dumps taken before a volume's files are copied."""

from __future__ import annotations

import sys

import pandas
from pandas.errors import EmptyDataError

from baudolo.databases import COLUMNS, DELIMITER

from .db import backup_database
from .docker import has_tool, image_id

DUMP_TOOLS: tuple[tuple[str, str], ...] = (
    ("postgres", "pg_dumpall"),
    ("mariadb", "mariadb-dump"),
    ("mariadb", "mysqldump"),
)

_ENGINE_BY_IMAGE: dict[str, tuple[str, str] | None] = {}


def container_engine(container: str) -> tuple[str, str] | None:
    """The (engine, dump tool) a container can serve, or None for neither.

    Asks the container what it can run instead of reading its image name. A
    dedicated Postgres is tagged `<app>-database` or `postgis/postgis` and
    carries no engine token at all, while a swarm registry host such as
    `svc-db-mariadb-swarm-mgr-01:5000` carries the wrong one.

    Args:
        container: must be running - `docker exec` is the probe, and a
            stopped container would be cached as "no engine" for its whole
            image. The only caller feeds it `docker ps` output.

    Returns:
        The engine and the tool that dumps it, cached per image ID so that
        replicas of one image are probed once.
    """
    image = image_id(container)
    if image not in _ENGINE_BY_IMAGE:
        _ENGINE_BY_IMAGE[image] = next(
            (
                (engine, tool)
                for engine, tool in DUMP_TOOLS
                if has_tool(container, tool)
            ),
            None,
        )
    return _ENGINE_BY_IMAGE[image]


def backup_mariadb_or_postgres(
    *,
    container: str,
    volume_dir: str,
    databases_df: pandas.DataFrame,
    database_containers: list[str],
) -> tuple[bool, bool]:
    """
    Returns (is_db_container, dumped_any)
    """
    engine = container_engine(container)
    if engine is None:
        return False, False
    db_type, dump_tool = engine
    dumped = backup_database(
        container=container,
        volume_dir=volume_dir,
        db_type=db_type,
        dump_tool=dump_tool,
        databases_df=databases_df,
        database_containers=database_containers,
    )
    return True, dumped


def _empty_databases_df() -> pandas.DataFrame:
    """
    Create an empty DataFrame with the expected schema for databases.csv.

    This allows the backup to continue without DB dumps when the CSV is missing
    or empty (pandas EmptyDataError).
    """
    return pandas.DataFrame(columns=list(COLUMNS))


def load_databases_df(csv_path: str) -> pandas.DataFrame:
    """
    Load databases.csv robustly.

    - Missing file     -> warn, continue with empty df
    - Empty file       -> warn, continue with empty df
    - Valid CSV        -> return dataframe
    """
    try:
        return pandas.read_csv(
            csv_path, sep=DELIMITER, keep_default_na=False, dtype=str
        )
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
    databases_df: pandas.DataFrame,
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
