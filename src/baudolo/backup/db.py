from __future__ import annotations

import os
import pathlib
import re
import logging
import pandas

from .shell import BackupException, execute_shell_command

log = logging.getLogger(__name__)


def get_instance(container: str, database_containers: list[str]) -> str:
    if container in database_containers:
        return container
    return re.split(r"(_|-)(database|db|postgres)", container)[0]


def fallback_pg_dumpall(container: str, username: str, password: str, out_file: str) -> None:
    cmd = (
        f"PGPASSWORD={password} docker exec -i {container} "
        f"pg_dumpall -U {username} -h localhost > {out_file}"
    )
    execute_shell_command(cmd)


def backup_database(
    *,
    container: str,
    volume_dir: str,
    db_type: str,
    databases_df: "pandas.DataFrame",
    database_containers: list[str],
) -> bool:
    """
    Returns True if at least one dump file was produced, else False.
    """
    instance_name = get_instance(container, database_containers)
    entries = databases_df.loc[databases_df["instance"] == instance_name]
    if entries.empty:
        log.warning("No entry found for instance '%s' (skipping DB dump)", instance_name)
        return False

    out_dir = os.path.join(volume_dir, "sql")
    pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)

    produced = False

    for row in entries.itertuples(index=False):
        db_name = row.database
        user = row.username
        password = row.password

        dump_file = os.path.join(out_dir, f"{db_name}.backup.sql")

        if db_type == "mariadb":
            cmd = (
                f"docker exec {container} /usr/bin/mariadb-dump "
                f"-u {user} -p{password} {db_name} > {dump_file}"
            )
            execute_shell_command(cmd)
            produced = True
            continue

        if db_type == "postgres":
            cluster_file = os.path.join(out_dir, f"{instance_name}.cluster.backup.sql")

            if not db_name:
                fallback_pg_dumpall(container, user, password, cluster_file)
                return True

            try:
                cmd = (
                    f"PGPASSWORD={password} docker exec -i {container} "
                    f"pg_dump -U {user} -d {db_name} -h localhost > {dump_file}"
                )
                execute_shell_command(cmd)
                produced = True
            except BackupException as e:
                print(f"pg_dump failed: {e}", flush=True)
                print(
                    f"Falling back to pg_dumpall for instance '{instance_name}'",
                    flush=True,
                )
                fallback_pg_dumpall(container, user, password, cluster_file)
                produced = True
            continue

    return produced
