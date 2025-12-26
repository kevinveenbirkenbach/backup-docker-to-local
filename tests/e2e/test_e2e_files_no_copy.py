import unittest

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


class TestE2EFilesNoCopy(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-files-nocopy")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)

        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        cls.volume_src = f"{cls.prefix}-vol-src"
        cls.volume_dst = f"{cls.prefix}-vol-dst"
        cls.containers = []
        cls.volumes = [cls.volume_src, cls.volume_dst]

        run(["docker", "volume", "create", cls.volume_src])
        run([
            "docker", "run", "--rm",
            "-v", f"{cls.volume_src}:/data",
            "alpine:3.20",
            "sh", "-lc", "echo 'hello' > /data/hello.txt",
        ])

        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(cls.databases_csv, [])

        # dump-only => NO file rsync backups
        backup_run(
            backups_dir=cls.backups_dir,
            repo_name=cls.repo_name,
            compose_dir=cls.compose_dir,
            databases_csv=cls.databases_csv,
            database_containers=["dummy-db"],
            images_no_stop_required=["alpine", "postgres", "mariadb", "mysql"],
            dump_only=True,
        )

        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    def test_files_backup_not_present(self) -> None:
        p = backup_path(self.backups_dir, self.repo_name, self.version, self.volume_src) / "files"
        self.assertFalse(p.exists(), f"Did not expect files backup dir at: {p}")

    def test_restore_files_fails_expected(self) -> None:
        p = run([
            "baudolo-restore", "files",
            self.volume_dst, self.hash, self.version,
            "--backups-dir", self.backups_dir,
            "--repo-name", self.repo_name,
        ], check=False)
        self.assertEqual(p.returncode, 2, f"Expected exitcode 2, got {p.returncode}\nSTDOUT={p.stdout}\nSTDERR={p.stderr}")
