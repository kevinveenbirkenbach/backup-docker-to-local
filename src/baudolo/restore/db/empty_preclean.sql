-- Owner-filtered pre-clean for `restore --empty`. Emitted as one DROP per row and
-- run via \gexec so each executes as its own top-level statement: a single DO-block
-- would run every DROP in one transaction and exhaust max_locks_per_transaction on
-- large schemas (e.g. gitlab). Also drops user-owned non-public schemas so a dump
-- that CREATE SCHEMAs (e.g. discourse's discourse_functions) does not fail on an
-- already-existing schema. Objects belonging to an extension are skipped: postgres
-- refuses to drop them one by one ("cannot drop function vector_in(...) because
-- extension vector requires it"), and the dump's CREATE EXTENSION IF NOT EXISTS
-- finds the surviving extension either way. Owning them is not enough to make them
-- droppable - an extension a role installed itself is owned by that role, so the
-- owner filter alone lets pgvector's members through.
SELECT format('DROP %s IF EXISTS public.%s CASCADE', obj.type, obj.name)
  FROM (
    SELECT format('%I', c.relname) AS name,
           CASE c.relkind
             WHEN 'v' THEN 'VIEW'
             WHEN 'm' THEN 'MATERIALIZED VIEW'
             WHEN 'f' THEN 'FOREIGN TABLE'
             ELSE 'TABLE'
           END AS type,
           c.oid AS objid, 'pg_class'::regclass AS classid
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
       AND pg_get_userbyid(c.relowner) = current_user
    UNION ALL
    -- Overloaded functions share a proname; DROP needs the identity
    -- signature or psql aborts with "function name is not unique".
    SELECT format('%I(%s)', p.proname, pg_get_function_identity_arguments(p.oid)) AS name,
           CASE p.prokind WHEN 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END AS type,
           p.oid AS objid, 'pg_proc'::regclass AS classid
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.prokind IN ('f', 'p', 'w')
       AND pg_get_userbyid(p.proowner) = current_user
    UNION ALL
    SELECT format('%I', c.relname) AS name, 'SEQUENCE' AS type,
           c.oid AS objid, 'pg_class'::regclass AS classid
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind = 'S'
       AND pg_get_userbyid(c.relowner) = current_user
    UNION ALL
    SELECT format('%I', t.typname) AS name, 'TYPE' AS type,
           t.oid AS objid, 'pg_type'::regclass AS classid
      FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
     WHERE n.nspname = 'public'
       AND pg_get_userbyid(t.typowner) = current_user
       AND (t.typtype IN ('e', 'd')
            OR (t.typtype = 'c' AND EXISTS (
                  SELECT 1 FROM pg_class c2
                   WHERE c2.oid = t.typrelid AND c2.relkind = 'c')))
    UNION ALL
    SELECT format('%I', col.collname) AS name, 'COLLATION' AS type,
           col.oid AS objid, 'pg_collation'::regclass AS classid
      FROM pg_collation col JOIN pg_namespace n ON n.oid = col.collnamespace
     WHERE n.nspname = 'public'
       AND pg_get_userbyid(col.collowner) = current_user
    UNION ALL
    SELECT format('%I', ts.cfgname) AS name, 'TEXT SEARCH CONFIGURATION' AS type,
           ts.oid AS objid, 'pg_ts_config'::regclass AS classid
      FROM pg_ts_config ts JOIN pg_namespace n ON n.oid = ts.cfgnamespace
     WHERE n.nspname = 'public'
       AND pg_get_userbyid(ts.cfgowner) = current_user
    UNION ALL
    SELECT format('%I', d.dictname) AS name, 'TEXT SEARCH DICTIONARY' AS type,
           d.oid AS objid, 'pg_ts_dict'::regclass AS classid
      FROM pg_ts_dict d JOIN pg_namespace n ON n.oid = d.dictnamespace
     WHERE n.nspname = 'public'
       AND pg_get_userbyid(d.dictowner) = current_user
  ) obj
 WHERE NOT EXISTS (
         SELECT 1 FROM pg_depend dep
          WHERE dep.classid = obj.classid AND dep.objid = obj.objid
            AND dep.deptype = 'e')
UNION ALL
SELECT format('DROP SCHEMA IF EXISTS %I CASCADE', n.nspname)
  FROM pg_namespace n
 WHERE NOT starts_with(n.nspname, 'pg_')
   AND n.nspname NOT IN ('public', 'information_schema')
   AND pg_get_userbyid(n.nspowner) = current_user
   AND NOT EXISTS (
         SELECT 1 FROM pg_depend dep
          WHERE dep.classid = 'pg_namespace'::regclass AND dep.objid = n.oid
            AND dep.deptype = 'e')
\gexec
