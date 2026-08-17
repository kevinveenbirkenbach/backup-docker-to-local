-- Pre-clean for `restore cluster --empty`. A pg_dumpall stream recreates roles
-- and databases, so replaying it into a populated cluster dies on the first
-- CREATE ROLE. Emitted as one DROP per row and run via \gexec so each executes
-- as its own top-level statement: DROP DATABASE cannot run inside a
-- transaction block, which rules out a single DO block.
-- The phase column pins the order: databases must be gone before their owners
-- can be dropped, and DROP OWNED BY releases what a role still holds in the
-- control database. Template databases, the control database itself, the pg_*
-- system roles and the connecting role are kept - the dump does not recreate
-- them and dropping them would end the session.
-- The sweep stays catalog-wide on purpose: a scoped one leaves databases that
-- pin a dumped role in pg_shdepend, and phase 3 then fails after phase 1 has
-- already dropped. assert_instance_matches_dump refuses before this runs.
SELECT statement
  FROM (
    SELECT 1 AS phase,
           format('DROP DATABASE IF EXISTS %I', datname) AS statement
      FROM pg_database
     WHERE NOT datistemplate
       AND datname <> current_database()
    UNION ALL
    SELECT 2, format('DROP OWNED BY %I', rolname)
      FROM pg_roles
     WHERE NOT starts_with(rolname, 'pg_')
       AND rolname <> current_user
    UNION ALL
    SELECT 3, format('DROP ROLE IF EXISTS %I', rolname)
      FROM pg_roles
     WHERE NOT starts_with(rolname, 'pg_')
       AND rolname <> current_user
  ) drops
 ORDER BY phase
\gexec
