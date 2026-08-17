from __future__ import annotations

import sys
from pathlib import Path

from baudolo.restore.run import docker_exec, docker_exec_sh

from .version import guard

_NO_CLIENT = "ERROR: neither 'mariadb' nor 'mysql' found in container."


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
    except Exception:
        print(_NO_CLIENT, file=sys.stderr)
        raise
    if not out:
        print(_NO_CLIENT, file=sys.stderr)
        raise RuntimeError("empty client detection output")
    return out


def restore_mariadb_sql(
    *,
    container: str,
    db_name: str,
    user: str,
    password: str,
    sql_path: str,
    empty: bool,
    check_version: bool = True,
) -> None:
    client = _pick_client(container)

    if not Path(sql_path).is_file():
        raise FileNotFoundError(sql_path)

    if check_version:
        guard(
            sql_path=sql_path,
            engine="mariadb",
            container=container,
            user=user,
            password=password,
            client=client,
        )

    if empty:
        # Do not hardcode 'mysql': MariaDB 11 images may not ship that binary.
        result = docker_exec(
            container,
            [
                client,
                "-u",
                user,
                f"--password={password}",
                "-N",
                "-e",
                f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{db_name}';",  # noqa: S608 - validate_database() constrains the name to ^[a-zA-Z0-9_][a-zA-Z0-9_-]*$
            ],
            capture=True,
        )
        tables = result.stdout.decode().split()

        if tables:
            # SET FOREIGN_KEY_CHECKS is session-scoped, so it must share one
            # client session with the DROPs or FK constraints still fire.
            drop_sql = (
                "SET FOREIGN_KEY_CHECKS=0; "
                + " ".join(
                    f"DROP TABLE IF EXISTS `{db_name}`.`{tbl}`;" for tbl in tables
                )
                + " SET FOREIGN_KEY_CHECKS=1;"
            )
            docker_exec(
                container,
                [
                    client,
                    "-u",
                    user,
                    f"--password={password}",
                    "-e",
                    drop_sql,
                ],
            )

    with Path(sql_path).open("rb") as f:
        docker_exec(
            container, [client, "-u", user, f"--password={password}", db_name], stdin=f
        )

    print(f"MariaDB/MySQL restore complete for db '{db_name}'.")
