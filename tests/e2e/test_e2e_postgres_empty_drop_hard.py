# tests/e2e/test_e2e_postgres_empty_drop_hard.py
import unittest

from .helpers import (
    POSTGRES_IMAGE,
    POSTGRES_DATA_DIR,
    backup_run,
    cleanup_docker,
    create_minimal_compose_dir,
    ensure_empty_dir,
    latest_version_dir,
    require_docker,
    run,
    unique,
    wait_for_postgres,
    write_databases_csv,
)

# The scenario the --empty pre-clean must survive: a non-public user schema
# plus one object of every class the discovery SELECT enumerates. Restore
# --empty runs against the still-populated DB (no wipe), so the pre-clean must
# drop discourse_functions too or the dump's CREATE SCHEMA aborts the replay
# under ON_ERROR_STOP; the old public-only DROP left it and broke discourse.
# The f()/f(int) pair reproduces discourse's overload abort ("function name
# is not unique") and english_stem_nostop reproduces taiga's text search
# dictionary abort (duplicate pg_ts_dict_dictname_index).
SCENARIO_SQL = (
    "CREATE SCHEMA discourse_functions;"
    "CREATE TABLE discourse_functions.helper (id int);"
    "INSERT INTO discourse_functions.helper VALUES (1);"
    "CREATE TABLE public.t (id int primary key, v text);"
    "INSERT INTO public.t VALUES (1, 'ok');"
    "CREATE VIEW public.t_view AS SELECT * FROM public.t;"
    "CREATE SEQUENCE public.s;"
    "CREATE TYPE public.mood AS ENUM ('ok', 'bad');"
    "CREATE FUNCTION public.f() RETURNS int LANGUAGE sql AS 'SELECT 1';"
    "CREATE FUNCTION public.f(i int) RETURNS int LANGUAGE sql AS 'SELECT i';"
    "CREATE COLLATION public.c (locale = 'C');"
    "CREATE TEXT SEARCH DICTIONARY public.english_stem_nostop"
    " (Template = snowball, Language = english);"
    "CREATE TEXT SEARCH CONFIGURATION public.english_nostop (COPY = english);"
    "ALTER TEXT SEARCH CONFIGURATION public.english_nostop"
    " ALTER MAPPING FOR asciiword WITH public.english_stem_nostop;"
)


class TestE2EPostgresEmptyDropHard(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-postgres-empty-drop-hard")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)
        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        cls.pg_container = f"{cls.prefix}-pg"
        cls.pg_volume = f"{cls.prefix}-pg-vol"
        cls.containers = [cls.pg_container]
        cls.volumes = [cls.pg_volume]

        run(["docker", "volume", "create", cls.pg_volume])
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cls.pg_container,
                "-e",
                "POSTGRES_PASSWORD=pgpw",
                "-e",
                "POSTGRES_DB=appdb",
                "-e",
                "POSTGRES_USER=postgres",
                "-v",
                f"{cls.pg_volume}:{POSTGRES_DATA_DIR}",
                POSTGRES_IMAGE,
            ]
        )
        wait_for_postgres(cls.pg_container, user="postgres", timeout_s=90)

        run(
            [
                "docker",
                "exec",
                cls.pg_container,
                "sh",
                "-lc",
                f'psql -U postgres -d appdb -v ON_ERROR_STOP=1 -c "{SCENARIO_SQL}"',
            ]
        )

        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(
            cls.databases_csv, [(cls.pg_container, "appdb", "postgres", "pgpw")]
        )
        backup_run(
            backups_dir=cls.backups_dir,
            repo_name=cls.repo_name,
            compose_dir=cls.compose_dir,
            databases_csv=cls.databases_csv,
            database_containers=[cls.pg_container],
            images_no_stop_required=[POSTGRES_IMAGE],
        )
        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

        # No wipe: restore --empty must pre-clean the fully-populated DB
        # (incl. the non-public schema) before replaying the dump.
        run(
            [
                "baudolo-restore",
                "postgres",
                cls.pg_volume,
                cls.hash,
                cls.version,
                "--backups-dir",
                cls.backups_dir,
                "--repo-name",
                cls.repo_name,
                "--container",
                cls.pg_container,
                "--db-name",
                "appdb",
                "--db-user",
                "postgres",
                "--db-password",
                "pgpw",
                "--empty",
            ]
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    def _scalar(self, sql: str) -> str:
        p = run(
            [
                "docker",
                "exec",
                self.pg_container,
                "sh",
                "-lc",
                f'psql -U postgres -d appdb -t -A -c "{sql}"',
            ]
        )
        return (p.stdout or "").strip()

    def test_public_data_restored(self) -> None:
        self.assertEqual(self._scalar("SELECT v FROM public.t WHERE id=1;"), "ok")

    def test_view_restored(self) -> None:
        self.assertEqual(self._scalar("SELECT count(*) FROM public.t_view;"), "1")

    def test_non_public_schema_restored(self) -> None:
        self.assertEqual(
            self._scalar(
                "SELECT count(*) FROM pg_namespace WHERE nspname='discourse_functions';"
            ),
            "1",
        )

    def test_overloaded_functions_restored_once_each(self) -> None:
        self.assertEqual(
            self._scalar("SELECT count(*) FROM pg_proc WHERE proname='f';"), "2"
        )
        self.assertEqual(self._scalar("SELECT public.f(41) + public.f();"), "42")

    def test_text_search_dictionary_restored_once(self) -> None:
        self.assertEqual(
            self._scalar(
                "SELECT count(*) FROM pg_ts_dict WHERE dictname='english_stem_nostop';"
            ),
            "1",
        )
        self.assertEqual(
            self._scalar(
                "SELECT count(*) FROM pg_ts_config WHERE cfgname='english_nostop';"
            ),
            "1",
        )


if __name__ == "__main__":
    unittest.main()
