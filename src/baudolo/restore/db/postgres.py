from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable, Iterator

from ..run import docker_exec

_SUPERUSER_ONLY_PREFIXES = (b"COMMENT ON EXTENSION", b"ALTER DEFAULT PRIVILEGES")


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
        # Owner-filtered pre-clean emitted as one DROP per row and run via \gexec so each
        # executes as its own top-level statement: a single DO-block runs every DROP in one
        # transaction and exhausts max_locks_per_transaction on large schemas (e.g. gitlab).
        # Also drop user-owned non-public schemas so a dump that CREATE SCHEMAs (e.g.
        # discourse's discourse_functions) does not fail on an already-existing schema.
        # Extension members (pg_trgm's set_limit) are superuser-owned; IF EXISTS absorbs CASCADE fallout.
        drop_sql = r"""
SELECT format('DROP %s IF EXISTS public.%s CASCADE', obj.type, obj.name)
  FROM (
    SELECT format('%I', c.relname) AS name,
           CASE c.relkind
             WHEN 'v' THEN 'VIEW'
             WHEN 'm' THEN 'MATERIALIZED VIEW'
             WHEN 'f' THEN 'FOREIGN TABLE'
             ELSE 'TABLE'
           END AS type
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
       AND pg_get_userbyid(c.relowner) = current_user
    UNION ALL
    -- Overloaded functions share a proname; DROP needs the identity
    -- signature or psql aborts with "function name is not unique".
    SELECT format('%I(%s)', p.proname, pg_get_function_identity_arguments(p.oid)) AS name,
           CASE p.prokind WHEN 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END AS type
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.prokind IN ('f', 'p', 'w')
       AND pg_get_userbyid(p.proowner) = current_user
    UNION ALL
    SELECT format('%I', c.relname) AS name, 'SEQUENCE' AS type
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind = 'S'
       AND pg_get_userbyid(c.relowner) = current_user
    UNION ALL
    SELECT format('%I', t.typname) AS name, 'TYPE' AS type
      FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
     WHERE n.nspname = 'public'
       AND pg_get_userbyid(t.typowner) = current_user
       AND (t.typtype IN ('e', 'd')
            OR (t.typtype = 'c' AND EXISTS (
                  SELECT 1 FROM pg_class c2
                   WHERE c2.oid = t.typrelid AND c2.relkind = 'c')))
    UNION ALL
    SELECT format('%I', col.collname) AS name, 'COLLATION' AS type
      FROM pg_collation col JOIN pg_namespace n ON n.oid = col.collnamespace
     WHERE n.nspname = 'public'
       AND pg_get_userbyid(col.collowner) = current_user
  ) obj
UNION ALL
SELECT format('DROP SCHEMA IF EXISTS %I CASCADE', n.nspname)
  FROM pg_namespace n
 WHERE NOT starts_with(n.nspname, 'pg_')
   AND n.nspname NOT IN ('public', 'information_schema')
   AND pg_get_userbyid(n.nspowner) = current_user
\gexec
"""
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
            ["psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", db_name],
            stdin=filtered,
            docker_env=docker_env,
        )

    print(f"PostgreSQL restore complete for db '{db_name}'.")
