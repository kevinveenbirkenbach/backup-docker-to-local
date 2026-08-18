from __future__ import annotations

import logging
import pathlib
import re
from typing import TYPE_CHECKING

from baudolo.databases import CLUSTER_ROW, validate_database
from baudolo.generation import CLUSTER_SUFFIX, DUMP_SUFFIX, SQL_DIR

from .docker import docker_exec_argv
from .shell import BackupError, execute_to_file

if TYPE_CHECKING:
    import pandas as pd

log = logging.getLogger(__name__)

ENGINE_NAMES = ("database", "postgres", "mariadb", "mysql", "db")
_SUFFIX_RE = re.compile(rf"(_|-)({'|'.join(ENGINE_NAMES)})")


def get_instance(container: str, database_containers: list[str]) -> str | None:
    """The databases.csv instance a container serves, or None for no database.

    A declared container is its own instance. Every other name is read against
    ENGINE_NAMES: carrying one as a suffix makes the rest the instance, which
    maps `<app>-database` from compose and `<app>_database.1.<task>` from swarm
    onto the same one; being one outright makes the container its own instance,
    the shape a compose file writes as `container_name: postgres`.

    Args:
        container: the running container's name.
        database_containers: names passed via --database-containers, taken as
            declared engines whatever they are called.

    Returns:
        The instance name, or None when the name neither carries nor is an
        engine name: an application container is not an engine, even when it
        ships the client tools that would let a dump command start.
    """
    if container in database_containers:
        return container
    parts = _SUFFIX_RE.split(container)
    if len(parts) > 1:
        return parts[0]
    return container if container in ENGINE_NAMES else None


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
            forward_env=["PGPASSWORD"],
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
    databases_df: pd.DataFrame,
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
    if instance_name is None:
        log.debug("Container '%s' carries no database token", container)
        return False

    entries = databases_df[databases_df["instance"] == instance_name]
    if entries.empty:
        log.debug("No database entries for instance '%s'", instance_name)
        return False

    out_dir = pathlib.Path(volume_dir) / SQL_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

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

            cluster_file = str(out_dir / f"{instance_name}{CLUSTER_SUFFIX}")
            fallback_pg_dumpall(container, user, password, cluster_file)
            produced = True
            continue

        db_name = db_value
        dump_file = str(out_dir / f"{db_name}{DUMP_SUFFIX}")

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
                        forward_env=["PGPASSWORD"],
                    ),
                    dump_file,
                    env={"PGPASSWORD": password},
                )
                produced = True
            except BackupError as e:
                raise BackupError(
                    f"Postgres dump failed for instance '{instance_name}', "
                    f"database '{db_name}'. This database was explicitly configured "
                    "and therefore must succeed.\n"
                    f"{e}"
                ) from e
            continue

    return produced
