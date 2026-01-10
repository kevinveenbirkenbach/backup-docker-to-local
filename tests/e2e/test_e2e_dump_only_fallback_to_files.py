# tests/e2e/test_e2e_dump_only_fallback_to_files.py
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
    write_databases_csv,
    wait_for_postgres,
)


class TestE2EDumpOnlyFallbackToFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-dump-only-sql-fallback")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)

        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        cls.pg_container = f"{cls.prefix}-pg"
        cls.pg_volume = f"{cls.prefix}-pg-vol"
        cls.restore_volume = f"{cls.prefix}-restore-vol"

        cls.containers = [cls.pg_container]
        cls.volumes = [cls.pg_volume, cls.restore_volume]

        run(["docker", "volume", "create", cls.pg_volume])

        # Start Postgres (creates a real DB volume)
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
                f"{cls.pg_volume}:/var/lib/postgresql/data",
                "postgres:16",
            ]
        )
        wait_for_postgres(cls.pg_container, user="postgres", timeout_s=90)

        # Add a deterministic marker file into the volume
        cls.marker = "dump-only-sql-fallback-marker"
        run(
            [
                "docker",
                "exec",
                cls.pg_container,
                "sh",
                "-lc",
                f"echo '{cls.marker}' > /var/lib/postgresql/data/marker.txt",
            ]
        )

        # databases.csv WITHOUT matching entry for this instance -> should skip dump
        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(cls.databases_csv, [])  # empty except header

        # Run baudolo with --dump-only-sql and a DB container present:
        # Expected: WARNING + FALLBACK to file backup (files/ must exist)
        cmd = [
            "baudolo",
            "--compose-dir",
            cls.compose_dir,
            "--docker-compose-hard-restart-required",
            "mailu",
            "--repo-name",
            cls.repo_name,
            "--databases-csv",
            cls.databases_csv,
            "--backups-dir",
            cls.backups_dir,
            "--database-containers",
            cls.pg_container,
            "--images-no-stop-required",
            "postgres",
            "mariadb",
            "mysql",
            "alpine",
            "--dump-only-sql",
        ]
        cp = run(cmd, capture=True, check=True)

        cls.stdout = cp.stdout or ""
        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

        # Restore files into a fresh volume to prove file backup happened
        run(["docker", "volume", "create", cls.restore_volume])
        run(
            [
                "baudolo-restore",
                "files",
                cls.restore_volume,
                cls.hash,
                cls.version,
                "--backups-dir",
                cls.backups_dir,
                "--repo-name",
                cls.repo_name,
                "--source-volume",
                cls.pg_volume,
                "--rsync-image",
                "ghcr.io/kevinveenbirkenbach/alpine-rsync",
            ]
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    def test_warns_about_missing_dump_in_dump_only_mode(self) -> None:
        self.assertIn(
            "WARNING: dump-only-sql requested but no DB dump was produced",
            self.stdout,
            f"Expected warning in baudolo output. STDOUT:\n{self.stdout}",
        )

    def test_files_backup_exists_due_to_fallback(self) -> None:
        p = (
            backup_path(
                self.backups_dir,
                self.repo_name,
                self.version,
                self.pg_volume,
            )
            / "files"
        )
        self.assertTrue(p.is_dir(), f"Expected files backup dir at: {p}")

    def test_sql_dump_not_present(self) -> None:
        # There should be no sql dumps because databases.csv had no matching entry.
        sql_dir = (
            backup_path(
                self.backups_dir,
                self.repo_name,
                self.version,
                self.pg_volume,
            )
            / "sql"
        )
        # Could exist (dir created) in some edge cases, but should contain no *.sql dumps.
        if sql_dir.exists():
            dumps = list(sql_dir.glob("*.sql"))
            self.assertEqual(
                len(dumps),
                0,
                f"Did not expect SQL dump files, found: {dumps}",
            )

    def test_restored_files_contain_marker(self) -> None:
        p = run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{self.restore_volume}:/data",
                "alpine:3.20",
                "sh",
                "-lc",
                "cat /data/marker.txt",
            ]
        )
        self.assertEqual((p.stdout or "").strip(), self.marker)
