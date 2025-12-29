from __future__ import annotations

import os
import pathlib
import re
import logging
from typing import Optional

import pandas

from .shell import BackupException, execute_shell_command

log = logging.getLogger(__name__)


def get_instance(container: str, database_containers: list[str]) -> str:
    """
    Derive a stable instance name from the container name.
    """
    if container in database_containers:
        return container
    return re.split(r"(_|-)(database|db|postgres)", container)[0]


def _validate_database_value(value: Optional[str], *, instance: str) -> str:
    """
    Enforce explicit database semantics:

    - "*"       => dump ALL databases (cluster dump for Postgres)
    - "<name>"  => dump exactly this database
    - ""        => invalid configuration (would previously result in NaN / nan.backup.sql)
    """
    v = (value or "").strip()
    if v == "":
        raise ValueError(
            f"Invalid databases.csv entry for instance '{instance}': "
            "column 'database' must be '*' or a concrete database name (not empty)."
        )
    return v


def _atomic_write_cmd(cmd: str, out_file: str) -> None:
    """
    Write dump output atomically:
    - write to <file>.tmp
    - rename to <file> only on success

    This prevents empty or partial dump files from being treated as valid backups.
    """
    tmp = f"{out_file}.tmp"
    execute_shell_command(f"{cmd} > {tmp}")
    execute_shell_command(f"mv {tmp} {out_file}")


def fallback_pg_dumpall(container: str, username: str, password: str, out_file: str) -> None:
    """
    Perform a full Postgres cluster dump using pg_dumpall.
    """
    cmd = (
        f"PGPASSWORD={password} docker exec -i {container} "
        f"pg_dumpall -U {username} -h localhost"
    )
    _atomic_write_cmd(cmd, out_file)


def backup_database(
    *,
    container: str,
    volume_dir: str,
    db_type: str,
    databases_df: "pandas.DataFrame",
    database_containers: list[str],
) -> bool:
    """
    Backup databases for a given DB container.

    Returns True if at least one dump was produced.
    """
    instance_name = get_instance(container, database_containers)

    entries = databases_df[databases_df["instance"] == instance_name]
    if entries.empty:
        log.debug("No database entries for instance '%s'", instance_name)
        return False

    out_dir = os.path.join(volume_dir, "sql")
    pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)

    produced = False

    for row in entries.itertuples(index=False):
        raw_db = getattr(row, "database", "")
        user = (getattr(row, "username", "") or "").strip()
        password = (getattr(row, "password", "") or "").strip()

        db_value = _validate_database_value(raw_db, instance=instance_name)

        # Explicit: dump ALL databases
        if db_value == "*":
            if db_type != "postgres":
                raise ValueError(
                    f"databases.csv entry for instance '{instance_name}': "
                    "'*' is currently only supported for Postgres."
                )

            cluster_file = os.path.join(
                out_dir, f"{instance_name}.cluster.backup.sql"
            )
            fallback_pg_dumpall(container, user, password, cluster_file)
            produced = True
            continue

        # Concrete database dump
        db_name = db_value
        dump_file = os.path.join(out_dir, f"{db_name}.backup.sql")

        if db_type == "mariadb":
            cmd = (
                f"docker exec {container} /usr/bin/mariadb-dump "
                f"-u {user} -p{password} {db_name}"
            )
            _atomic_write_cmd(cmd, dump_file)
            produced = True
            continue

        if db_type == "postgres":
            try:
                cmd = (
                    f"PGPASSWORD={password} docker exec -i {container} "
                    f"pg_dump -U {user} -d {db_name} -h localhost"
                )
                _atomic_write_cmd(cmd, dump_file)
                produced = True
            except BackupException as e:
                # Explicit DB dump failed -> hard error
                raise BackupException(
                    f"Postgres dump failed for instance '{instance_name}', "
                    f"database '{db_name}'. This database was explicitly configured "
                    "and therefore must succeed.\n"
                    f"{e}"
                )
            continue

    return produced
