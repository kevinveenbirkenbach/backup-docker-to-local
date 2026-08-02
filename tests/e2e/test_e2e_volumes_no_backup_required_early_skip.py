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


class TestE2EVolumesNoBackupRequiredEarlySkip(unittest.TestCase):
    """Both volumes hang off the same container, so an image-level exclusion
    could only drop both. Only the named one may disappear."""

    @classmethod
    def setUpClass(cls) -> None:
        require_docker()

        cls.prefix = unique("baudolo-e2e-early-skip-no-backup-volume")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)

        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        cls.container = f"{cls.prefix}-app"
        cls.excluded_volume = f"{cls.prefix}-derived-vol"
        cls.kept_volume = f"{cls.prefix}-state-vol"

        cls.containers = [cls.container]
        cls.volumes = [cls.excluded_volume, cls.kept_volume]

        run(["docker", "volume", "create", cls.excluded_volume])
        run(["docker", "volume", "create", cls.kept_volume])

        run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{cls.excluded_volume}:/derived",
                "-v",
                f"{cls.kept_volume}:/state",
                "alpine:3.20",
                "sh",
                "-lc",
                "echo derived > /derived/derived.txt && echo state > /state/state.txt",
            ]
        )

        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cls.container,
                "-v",
                f"{cls.excluded_volume}:/derived",
                "-v",
                f"{cls.kept_volume}:/state",
                "alpine:3.20",
                "sleep",
                "600",
            ]
        )

        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(cls.databases_csv, [])

        cmd = [
            "baudolo",
            "--compose-dir",
            cls.compose_dir,
            "--repo-name",
            cls.repo_name,
            "--databases-csv",
            cls.databases_csv,
            "--backups-dir",
            cls.backups_dir,
            "--images-no-stop-required",
            "alpine:3.20",
            "--volumes-no-backup-required",
            cls.excluded_volume,
        ]
        cp = run(cmd, capture=True, check=True)
        cls.stdout = cp.stdout or ""
        cls.stderr = cp.stderr or ""

        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    def test_excluded_volume_has_no_backup_directory_at_all(self) -> None:
        p = backup_path(
            self.backups_dir,
            self.repo_name,
            self.version,
            self.excluded_volume,
        )
        self.assertFalse(
            p.exists(),
            f"Expected NO backup directory for the excluded volume, but found: {p}",
        )

    def test_sibling_volume_of_the_same_container_is_still_backed_up(self) -> None:
        p = (
            backup_path(
                self.backups_dir,
                self.repo_name,
                self.version,
                self.kept_volume,
            )
            / "files"
            / "state.txt"
        )
        self.assertTrue(p.is_file(), f"Expected backed up file at: {p}")
