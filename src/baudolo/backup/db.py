from __future__ import annotations

import logging
import os
import pathlib
import re

import pandas

from baudolo.databases import CLUSTER_ROW, validate_database

from .docker import docker_exec_argv
from .shell import BackupException, execute_to_file

log = logging.getLogger(__name__)


def get_instance(container: str, database_containers: list[str]) -> str:
    """
    Derive a stable instance name from the container name.
    """
    if container in database_containers:
        return container
    return re.split(r"(_|-)(database|db|postgres)", container)[0]


def fallback_pg_dumpall(
    container: str, username: str, password: str, out_file: str
) -> None:
    """
    Perform a full Postgres cluster dump using pg_dumpall.
    """
    execute_to_file(
        docker_exec_argv(
            container,
            ["pg_dumpall", "-U", username, "-h", "localhost"],
            interactive=True,
        ),
        out_file,
        env={"PGPASSWORD": password},
    )


def backup_database(
    *,
    container: str,
    volume_dir: str,
    db_type: str,
    dump_tool: str,
    databases_df: pandas.DataFrame,
    database_containers: list[str],
) -> bool:
    """
    Backup databases for a given DB container.

    Args:
        dump_tool: the MariaDB client found in the container, so an image
            that ships only mysqldump is dumped with the tool it has.

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

        db_value = validate_database(raw_db, instance=instance_name)

        if db_value == CLUSTER_ROW:
            if db_type != "postgres":
                raise ValueError(
                    f"databases.csv entry for instance '{instance_name}': "
                    f"'{CLUSTER_ROW}' is currently only supported for Postgres."
                )

            cluster_file = os.path.join(out_dir, f"{instance_name}.cluster.backup.sql")
            fallback_pg_dumpall(container, user, password, cluster_file)
            produced = True
            continue

        db_name = db_value
        dump_file = os.path.join(out_dir, f"{db_name}.backup.sql")

        if db_type == "mariadb":
            # Force TCP so auth matches '<user>'@'%' instead of socket -> 'localhost'.
            execute_to_file(
                docker_exec_argv(
                    container,
                    [
                        dump_tool,
                        "-h",
                        "127.0.0.1",
                        "--protocol=tcp",
                        "-u",
                        user,
                        f"-p{password}",
                        db_name,
                    ],
                ),
                dump_file,
            )
            produced = True
            continue

        if db_type == "postgres":
            try:
                execute_to_file(
                    docker_exec_argv(
                        container,
                        [
                            "pg_dump",
                            "-U",
                            user,
                            "-d",
                            db_name,
                            "-h",
                            "localhost",
                            "--no-owner",
                            "--no-privileges",
                        ],
                        interactive=True,
                    ),
                    dump_file,
                    env={"PGPASSWORD": password},
                )
                produced = True
            except BackupException as e:
                raise BackupException(
                    f"Postgres dump failed for instance '{instance_name}', "
                    f"database '{db_name}'. This database was explicitly configured "
                    "and therefore must succeed.\n"
                    f"{e}"
                )
            continue

    return produced
