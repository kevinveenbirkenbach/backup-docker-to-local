# tests/e2e/test_e2e_images_no_backup_required_early_skip.py
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
)


class TestE2EImagesNoBackupRequiredEarlySkip(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()

        cls.prefix = unique("baudolo-e2e-early-skip-no-backup-required")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)

        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        # --- Docker resources ---
        cls.redis_container = f"{cls.prefix}-redis"
        cls.ignored_volume = f"{cls.prefix}-redis-vol"
        cls.normal_volume = f"{cls.prefix}-files-vol"

        cls.containers = [cls.redis_container]
        cls.volumes = [cls.ignored_volume, cls.normal_volume]

        # Create volumes
        run(["docker", "volume", "create", cls.ignored_volume])
        run(["docker", "volume", "create", cls.normal_volume])

        # Start redis container using the ignored volume
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cls.redis_container,
                "-v",
                f"{cls.ignored_volume}:/data",
                "redis:alpine",
            ]
        )

        # Put deterministic content into the normal volume
        run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{cls.normal_volume}:/data",
                "alpine:3.20",
                "sh",
                "-lc",
                "mkdir -p /data && echo 'hello' > /data/hello.txt",
            ]
        )

        # databases.csv required by CLI (can be empty)
        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(cls.databases_csv, [])

        # Run baudolo with images-no-backup-required redis
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
            "dummy-db",
            "--images-no-stop-required",
            "alpine",
            "redis",
            "postgres",
            "mariadb",
            "mysql",
            "--images-no-backup-required",
            "redis",
        ]
        cp = run(cmd, capture=True, check=True)
        cls.stdout = cp.stdout or ""
        cls.stderr = cp.stderr or ""

        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    def test_ignored_volume_has_no_backup_directory_at_all(self) -> None:
        p = backup_path(
            self.backups_dir,
            self.repo_name,
            self.version,
            self.ignored_volume,
        )
        self.assertFalse(
            p.exists(),
            f"Expected NO backup directory to be created for ignored volume, but found: {p}",
        )

    def test_normal_volume_is_still_backed_up(self) -> None:
        p = (
            backup_path(
                self.backups_dir,
                self.repo_name,
                self.version,
                self.normal_volume,
            )
            / "files"
            / "hello.txt"
        )
        self.assertTrue(p.is_file(), f"Expected backed up file at: {p}")
