import unittest
from pathlib import Path

from .helpers import (
    backup_run,
    backup_path,
    cleanup_docker,
    create_minimal_compose_dir,
    ensure_empty_dir,
    latest_version_dir,
    require_docker,
    unique,
    write_databases_csv,
    run,
)


class TestE2EFilesFull(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-files-full")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)

        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        cls.volume_src = f"{cls.prefix}-vol-src"
        cls.volume_dst = f"{cls.prefix}-vol-dst"
        cls.containers = []
        cls.volumes = [cls.volume_src, cls.volume_dst]

        # create source volume with a file
        run(["docker", "volume", "create", cls.volume_src])
        run([
            "docker", "run", "--rm",
            "-v", f"{cls.volume_src}:/data",
            "alpine:3.20",
            "sh", "-lc", "mkdir -p /data && echo 'hello' > /data/hello.txt",
        ])

        # databases.csv (unused, but required by CLI)
        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(cls.databases_csv, [])

        # Run backup (files should be copied)
        backup_run(
            backups_dir=cls.backups_dir,
            repo_name=cls.repo_name,
            compose_dir=cls.compose_dir,
            databases_csv=cls.databases_csv,
            database_containers=["dummy-db"],
            images_no_stop_required=["alpine", "postgres", "mariadb", "mysql"],
        )

        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    def test_files_backup_exists(self) -> None:
        p = backup_path(self.backups_dir, self.repo_name, self.version, self.volume_src) / "files" / "hello.txt"
        self.assertTrue(p.is_file(), f"Expected backed up file at: {p}")

    def test_restore_files_into_new_volume(self) -> None:
        # restore files into dst volume
        run([
            "baudolo-restore", "files",
            self.volume_dst, self.hash, self.version,
            "--backups-dir", self.backups_dir,
            "--repo-name", self.repo_name,
            "--rsync-image", "ghcr.io/kevinveenbirkenbach/alpine-rsync",
        ])

        # verify restored file exists in dst volume
        p = run([
            "docker", "run", "--rm",
            "-v", f"{self.volume_dst}:/data",
            "alpine:3.20",
            "sh", "-lc", "cat /data/hello.txt",
        ])
        self.assertEqual((p.stdout or "").strip(), "hello")
