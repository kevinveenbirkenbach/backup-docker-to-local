"""Database dumps taken before a volume's files are copied."""

from __future__ import annotations

import sys
from typing import NamedTuple

import pandas as pd
from pandas.errors import EmptyDataError

from baudolo.databases import COLUMNS, DELIMITER

from .db import backup_database, get_instance
from .docker import has_tool, image_id

DUMP_TOOLS: tuple[tuple[str, str], ...] = (
    ("postgres", "pg_dumpall"),
    ("mariadb", "mariadb-dump"),
    ("mariadb", "mysqldump"),
)

_ENGINE_BY_IMAGE: dict[str, tuple[str, str] | None] = {}


class VolumeOutcome(NamedTuple):
    """What a dump attempt established about one volume.

    ``database`` says a container serving the volume speaks an engine this
    tool can dump; ``dumped`` says a dump was actually written. ``engine`` is
    the engine that was detected, or None when none was.
    """

    database: bool
    dumped: bool
    engine: str | None = None


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
    databases_df: pd.DataFrame,
    database_containers: list[str],
) -> VolumeOutcome:
    """What this container contributes to its volume's outcome."""
    engine = container_engine(container)
    if engine is None:
        return VolumeOutcome(database=False, dumped=False)
    if get_instance(container, database_containers) is None:
        return VolumeOutcome(database=False, dumped=False)
    db_type, dump_tool = engine
    dumped = backup_database(
        container=container,
        volume_dir=volume_dir,
        db_type=db_type,
        dump_tool=dump_tool,
        databases_df=databases_df,
        database_containers=database_containers,
    )
    return VolumeOutcome(database=True, dumped=dumped, engine=db_type)


def _empty_databases_df() -> pd.DataFrame:
    """
    Create an empty DataFrame with the expected schema for databases.csv.

    This allows the backup to continue without DB dumps when the CSV is missing
    or empty (pandas EmptyDataError).
    """
    return pd.DataFrame(columns=list(COLUMNS))


def load_databases_df(csv_path: str) -> pd.DataFrame:
    """
    Load databases.csv robustly.

    - Missing file     -> warn, continue with empty df
    - Empty file       -> warn, continue with empty df
    - Valid CSV        -> return dataframe
    """
    try:
        return pd.read_csv(csv_path, sep=DELIMITER, keep_default_na=False, dtype=str)
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
    databases_df: pd.DataFrame,
    database_containers: list[str],
) -> VolumeOutcome:
    """The volume's outcome across every container that mounts it."""
    found_db = False
    dumped_any = False
    engine: str | None = None

    for c in containers:
        outcome = backup_mariadb_or_postgres(
            container=c,
            volume_dir=vol_dir,
            databases_df=databases_df,
            database_containers=database_containers,
        )
        if outcome.database:
            found_db = True
        if outcome.dumped:
            dumped_any = True
        if engine is None:
            engine = outcome.engine

    return VolumeOutcome(database=found_db, dumped=dumped_any, engine=engine)
