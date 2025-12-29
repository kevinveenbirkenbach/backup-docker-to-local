import unittest

from .helpers import (
    backup_path,
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


class TestE2EDumpOnlySqlMixedRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-dump-only-sql-mixed-run")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)

        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        # --- Volumes ---
        cls.db_volume = f"{cls.prefix}-vol-db"
        cls.files_volume = f"{cls.prefix}-vol-files"

        # Track for cleanup
        cls.containers: list[str] = []
        cls.volumes = [cls.db_volume, cls.files_volume]

        # Create volumes
        run(["docker", "volume", "create", cls.db_volume])
        run(["docker", "volume", "create", cls.files_volume])

        # Put a marker into the non-db volume
        run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{cls.files_volume}:/data",
                "alpine:3.20",
                "sh",
                "-lc",
                "echo 'hello-non-db' > /data/hello.txt",
            ]
        )

        # --- Start Postgres container using the DB volume ---
        cls.pg_container = f"{cls.prefix}-pg"
        cls.containers.append(cls.pg_container)

        cls.pg_password = "postgres"
        cls.pg_db = "testdb"
        cls.pg_user = "postgres"

        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cls.pg_container,
                "-e",
                f"POSTGRES_PASSWORD={cls.pg_password}",
                "-v",
                f"{cls.db_volume}:/var/lib/postgresql/data",
                "postgres:16-alpine",
            ]
        )
        wait_for_postgres(cls.pg_container, user="postgres", timeout_s=90)

        # Create deterministic content in DB so dump is non-empty
        run(
            [
                "docker",
                "exec",
                cls.pg_container,
                "sh",
                "-lc",
                f'psql -U postgres -c "CREATE DATABASE {cls.pg_db};" || true',
            ],
            check=True,
        )
        run(
            [
                "docker",
                "exec",
                cls.pg_container,
                "sh",
                "-lc",
                (
                    f'psql -U postgres -d {cls.pg_db} -c '
                    '"CREATE TABLE IF NOT EXISTS t (id INT PRIMARY KEY, v TEXT);'
                    "INSERT INTO t(id,v) VALUES (1,'hello-db') "
                    "ON CONFLICT (id) DO UPDATE SET v=EXCLUDED.v;\""
                ),
            ],
            check=True,
        )

        # databases.csv with an entry => dump should succeed
        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(
            cls.databases_csv,
            [(cls.pg_container, cls.pg_db, cls.pg_user, cls.pg_password)],
        )

        # Run baudolo with dump-only-sql
        cmd = [
            "baudolo",
            "--compose-dir",
            cls.compose_dir,
            "--databases-csv",
            cls.databases_csv,
            "--database-containers",
            cls.pg_container,
            "--images-no-stop-required",
            "alpine",
            "postgres",
            "mariadb",
            "mysql",
            "--dump-only-sql",
            "--backups-dir",
            cls.backups_dir,
            "--repo-name",
            cls.repo_name,
        ]
        cp = run(cmd, capture=True, check=True)
        cls.stdout = cp.stdout
        cls.stderr = cp.stderr

        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    def test_db_volume_has_dump_and_no_files_dir(self) -> None:
        base = backup_path(self.backups_dir, self.repo_name, self.version, self.db_volume)

        dumps = base / "dumps"
        files = base / "files"

        self.assertTrue(dumps.exists(), f"Expected dumps dir for DB volume at: {dumps}")
        self.assertFalse(
            files.exists(),
            f"Did not expect files dir for DB volume when dump succeeded at: {files}",
        )

        # Optional: at least one dump file exists
        dump_files = list(dumps.glob("*.sql")) + list(dumps.glob("*.sql.gz"))
        self.assertTrue(
            dump_files,
            f"Expected at least one SQL dump file in {dumps}, found none.",
        )

    def test_non_db_volume_has_files_dir(self) -> None:
        base = backup_path(
            self.backups_dir, self.repo_name, self.version, self.files_volume
        )
        files = base / "files"
        self.assertTrue(
            files.exists(),
            f"Expected files dir for non-DB volume at: {files}",
        )

    def test_dump_only_sql_does_not_disable_non_db_files_backup(self) -> None:
        # Regression guard: even with --dump-only-sql, non-DB volumes must still be backed up as files
        base = backup_path(
            self.backups_dir, self.repo_name, self.version, self.files_volume
        )
        self.assertTrue(
            (base / "files").exists(),
            f"Expected non-DB volume files backup to exist at: {base / 'files'}",
        )
