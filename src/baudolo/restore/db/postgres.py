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
        # Owner-filtered: extension members (pg_trgm's set_limit) are superuser-owned; IF EXISTS absorbs CASCADE fallout.
        drop_sql = r"""
DO $$ DECLARE r RECORD;
BEGIN
  FOR r IN (
    SELECT c.relname AS name,
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
    SELECT p.proname AS name,
           CASE p.prokind WHEN 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END AS type
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.prokind IN ('f', 'p', 'w')
       AND pg_get_userbyid(p.proowner) = current_user
    UNION ALL
    SELECT c.relname AS name, 'SEQUENCE' AS type
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind = 'S'
       AND pg_get_userbyid(c.relowner) = current_user
    UNION ALL
    SELECT t.typname AS name, 'TYPE' AS type
      FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
     WHERE n.nspname = 'public'
       AND pg_get_userbyid(t.typowner) = current_user
       AND (t.typtype IN ('e', 'd')
            OR (t.typtype = 'c' AND EXISTS (
                  SELECT 1 FROM pg_class c2
                   WHERE c2.oid = t.typrelid AND c2.relkind = 'c')))
  ) LOOP
    EXECUTE format('DROP %s IF EXISTS public.%I CASCADE', r.type, r.name);
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
        raw_sql = f.read()
    # COMMENT ON EXTENSION and ALTER DEFAULT PRIVILEGES are superuser-only;
    # app-level restores must skip them or ON_ERROR_STOP aborts the replay.
    superuser_only = (b"COMMENT ON EXTENSION", b"ALTER DEFAULT PRIVILEGES")
    sql = b"\n".join(
        line for line in raw_sql.splitlines() if not line.startswith(superuser_only)
    )
    docker_exec(
        container,
        ["psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", db_name],
        stdin=sql,
        docker_env=docker_env,
    )

    print(f"PostgreSQL restore complete for db '{db_name}'.")
