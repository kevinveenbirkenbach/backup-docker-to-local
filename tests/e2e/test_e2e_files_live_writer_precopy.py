"""A writer that shrinks files mid-read fails the live pre-copy, not the run."""

import unittest

from .helpers import (
    backup_path,
    backup_run,
    cleanup_docker,
    create_minimal_compose_dir,
    ensure_empty_dir,
    latest_version_dir,
    require_docker,
    run,
    unique,
    wait_for_log,
    write_databases_csv,
)

CHURN_FILES = 8

WRITER = f"""
trap 'exit 0' TERM
echo hello > /data/hello.txt
for i in $(seq 1 {CHURN_FILES}); do
  (while :; do truncate -s 0 /data/churn$i; truncate -s 16M /data/churn$i; done) &
done
echo ready
wait
"""


class TestE2EFilesLiveWriterPreCopy(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-live-writer")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)

        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        cls.volume = f"{cls.prefix}-vol"
        cls.writer = f"{cls.prefix}-writer"
        cls.containers = [cls.writer]
        cls.volumes = [cls.volume]

        run(["docker", "volume", "create", cls.volume])
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cls.writer,
                "-v",
                f"{cls.volume}:/data",
                "alpine:3.20",
                "sh",
                "-c",
                WRITER,
            ]
        )
        wait_for_log(cls.writer, "ready")

        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(cls.databases_csv, [])

        cls.result = backup_run(
            backups_dir=cls.backups_dir,
            repo_name=cls.repo_name,
            compose_dir=cls.compose_dir,
            databases_csv=cls.databases_csv,
            database_containers=["dummy-db"],
            images_no_stop_required=["dummy-image"],
        )

        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    def test_the_live_pre_copy_hit_the_writer(self) -> None:
        self.assertIn(
            f"WARNING: live pre-copy of volume '{self.volume}' failed",
            self.result.stdout,
            "the writer never shrank a file under rsync, so this run proves nothing",
        )

    def test_the_stopped_copy_captured_the_volume(self) -> None:
        files = (
            backup_path(self.backups_dir, self.repo_name, self.version, self.volume)
            / "files"
        )
        self.assertEqual((files / "hello.txt").read_text().strip(), "hello")
        self.assertEqual(
            sorted(p.name for p in files.glob("churn*")),
            sorted(f"churn{i}" for i in range(1, CHURN_FILES + 1)),
        )

    def test_the_writer_runs_again_after_the_backup(self) -> None:
        state = run(
            ["docker", "inspect", "-f", "{{.State.Running}}", self.writer]
        ).stdout.strip()
        self.assertEqual(state, "true")


if __name__ == "__main__":
    unittest.main()
