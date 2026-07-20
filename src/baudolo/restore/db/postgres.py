from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable, Iterator

from ..run import docker_exec

_SUPERUSER_ONLY_PREFIXES = (b"COMMENT ON EXTENSION", b"ALTER DEFAULT PRIVILEGES")
_EMPTY_PRECLEAN_SQL = os.path.join(os.path.dirname(__file__), "empty_preclean.sql")


def filter_superuser_only_lines(lines: Iterable[bytes]) -> Iterator[bytes]:
    """Drop superuser-only statements an app-level psql replay cannot run.

    Args:
        lines: dump lines including their trailing newlines.

    Yields:
        Every line except top-level statements starting with a superuser-only
        prefix. Lines inside COPY ... FROM stdin data blocks are passed
        through untouched: a data row may legally start with the same bytes,
        and dropping it would silently corrupt the restored table.
    """
    in_copy = False
    for line in lines:
        if in_copy:
            yield line
            if line.rstrip(b"\r\n") == b"\\.":
                in_copy = False
            continue
        if line.startswith(b"COPY ") and line.rstrip(b"\r\n").endswith(b"FROM stdin;"):
            in_copy = True
            yield line
            continue
        if line.startswith(_SUPERUSER_ONLY_PREFIXES):
            continue
        yield line


def restore_postgres_sql(
    *,
    container: str,
    db_name: str,
    user: str,
    password: str,
    sql_path: str,
    empty: bool,
) -> None:
    if not os.path.isfile(sql_path):
        raise FileNotFoundError(sql_path)

    # Make password available INSIDE the container for psql.
    docker_env = {"PGPASSWORD": password}

    if empty:
        with open(_EMPTY_PRECLEAN_SQL, encoding="utf-8") as preclean:
            drop_sql = preclean.read()
        docker_exec(
            container,
            ["psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", db_name],
            stdin=drop_sql.encode(),
            docker_env=docker_env,
        )

    # Filter into a spooled temp file instead of building the whole dump in
    # memory: production dumps reach many GB and the previous read/splitlines/
    # join needed roughly three times the dump size in RSS.
    with open(sql_path, "rb") as src, tempfile.TemporaryFile() as filtered:
        for line in filter_superuser_only_lines(src):
            filtered.write(line)
        filtered.seek(0)
        docker_exec(
            container,
            [
                "psql",
                "--single-transaction",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                user,
                "-d",
                db_name,
            ],
            stdin=filtered,
            docker_env=docker_env,
        )

    print(f"PostgreSQL restore complete for db '{db_name}'.")
