from __future__ import annotations

import os
import sys

from ..run import docker_exec, docker_exec_sh


def _pick_client(container: str) -> str:
    """
    Prefer 'mariadb', fallback to 'mysql'.
    Some MariaDB images no longer ship a 'mysql' binary, so we must not assume it exists.
    """
    script = r"""
set -eu
if command -v mariadb >/dev/null 2>&1; then echo mariadb; exit 0; fi
if command -v mysql   >/dev/null 2>&1; then echo mysql;   exit 0; fi
exit 42
"""
    try:
        out = docker_exec_sh(container, script, capture=True).stdout.decode().strip()
        if not out:
            raise RuntimeError("empty client detection output")
        return out
    except Exception as e:
        print(
            "ERROR: neither 'mariadb' nor 'mysql' found in container.", file=sys.stderr
        )
        raise e


def restore_mariadb_sql(
    *,
    container: str,
    db_name: str,
    user: str,
    password: str,
    sql_path: str,
    empty: bool,
) -> None:
    client = _pick_client(container)

    if not os.path.isfile(sql_path):
        raise FileNotFoundError(sql_path)

    if empty:
        # IMPORTANT:
        # Do NOT hardcode 'mysql' here. Use the detected client.
        # MariaDB 11 images may not contain the mysql binary at all.
        docker_exec(
            container,
            [
                client,
                "-u",
                user,
                f"--password={password}",
                "-e",
                "SET FOREIGN_KEY_CHECKS=0;",
            ],
        )

        result = docker_exec(
            container,
            [
                client,
                "-u",
                user,
                f"--password={password}",
                "-N",
                "-e",
                f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{db_name}';",
            ],
            capture=True,
        )
        tables = result.stdout.decode().split()

        for tbl in tables:
            docker_exec(
                container,
                [
                    client,
                    "-u",
                    user,
                    f"--password={password}",
                    "-e",
                    f"DROP TABLE IF EXISTS `{db_name}`.`{tbl}`;",
                ],
            )

        docker_exec(
            container,
            [
                client,
                "-u",
                user,
                f"--password={password}",
                "-e",
                "SET FOREIGN_KEY_CHECKS=1;",
            ],
        )

    with open(sql_path, "rb") as f:
        docker_exec(
            container, [client, "-u", user, f"--password={password}", db_name], stdin=f
        )

    print(f"MariaDB/MySQL restore complete for db '{db_name}'.")
