# tests/e2e/test_e2e_postgres_single_transaction_live_writer.py
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

# The discourse restore-drill race: `restore --empty` replays the dump into a
# LIVE database while a background writer keeps touching a primary-key row
# (discourse's mini_scheduler upserts scheduler_stats(id=1)). Without a
# single-transaction replay, the pre-clean drops the table, the replay recreates
# it and auto-commits, the writer wins the gap and inserts id=1, and the dump's
# COPY of the same id then aborts with a duplicate-key violation under
# ON_ERROR_STOP -> the whole restore fails. The --single-transaction replay keeps
# the recreated table invisible until commit, so the writer can never insert the
# racing row and the restore completes. A wide filler table makes the COPY slow
# enough that the non-transactional variant loses the race deterministically.
SEED_SQL = (
    "CREATE TABLE public.scheduler_stats (id int primary key, v text);"
    "INSERT INTO public.scheduler_stats VALUES (1, 'from-dump');"
    "CREATE TABLE public.filler (id serial primary key, blob text);"
    "INSERT INTO public.filler (blob)"
    " SELECT repeat('x', 512) FROM generate_series(1, 100000);"
)

WRITER_LOOP = (
    "while true; do "
    "psql -h 127.0.0.1 -U postgres -d appdb "
    "-c \"INSERT INTO public.scheduler_stats(id, v) VALUES (1, 'live') "
    'ON CONFLICT (id) DO NOTHING;" >/dev/null 2>&1; '
    "done"
)


class TestE2EPostgresSingleTransactionLiveWriter(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-pg-single-txn")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)
        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        cls.pg_container = f"{cls.prefix}-pg"
        cls.pg_volume = f"{cls.prefix}-pg-vol"
        cls.writer = f"{cls.prefix}-writer"
        cls.containers = [cls.pg_container, cls.writer]
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
                f'psql -U postgres -d appdb -v ON_ERROR_STOP=1 -c "{SEED_SQL}"',
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

        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cls.writer,
                "--network",
                f"container:{cls.pg_container}",
                "-e",
                "PGPASSWORD=pgpw",
                POSTGRES_IMAGE,
                "sh",
                "-lc",
                WRITER_LOOP,
            ]
        )

        cls.restore = run(
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
            ],
            capture=True,
            check=False,
        )

        run(["docker", "rm", "-f", cls.writer], capture=True, check=False)

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

    def test_restore_survived_the_live_writer(self) -> None:
        self.assertEqual(
            self.restore.returncode,
            0,
            f"restore aborted (duplicate-key race not contained):\n{self.restore.stderr}",
        )

    def test_primary_key_row_restored(self) -> None:
        self.assertEqual(
            self._scalar("SELECT count(*) FROM public.scheduler_stats WHERE id=1;"),
            "1",
        )


if __name__ == "__main__":
    unittest.main()
