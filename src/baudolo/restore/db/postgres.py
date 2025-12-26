from __future__ import annotations

import os

from ..run import docker_exec


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
        drop_sql = r"""
DO $$ DECLARE r RECORD;
BEGIN
  FOR r IN (
    SELECT table_name AS name, 'TABLE' AS type FROM information_schema.tables WHERE table_schema='public'
    UNION ALL
    SELECT routine_name AS name, 'FUNCTION' AS type FROM information_schema.routines WHERE specific_schema='public'
    UNION ALL
    SELECT sequence_name AS name, 'SEQUENCE' AS type FROM information_schema.sequences WHERE sequence_schema='public'
  ) LOOP
    EXECUTE format('DROP %s public.%I CASCADE', r.type, r.name);
  END LOOP;
END $$;
"""
        docker_exec(
            container,
            ["psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", db_name],
            stdin=drop_sql.encode(),
            docker_env=docker_env,
        )

    with open(sql_path, "rb") as f:
        docker_exec(
            container,
            ["psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", db_name],
            stdin=f,
            docker_env=docker_env,
        )

    print(f"PostgreSQL restore complete for db '{db_name}'.")
