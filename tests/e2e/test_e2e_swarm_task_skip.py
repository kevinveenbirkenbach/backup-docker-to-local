# tests/e2e/test_e2e_swarm_task_skip.py
#
# Reproduces the swarm flake fixed on this branch: baudolo used to stop a
# swarm task container around the volume file backup because its image was
# not whitelisted; the orchestrator immediately replaced the stopped task and
# the later `docker start` failed on the detached overlay network, killing
# the backup run. With the fix the task container is skipped (backed up hot):
# the backup succeeds, the very same container instance keeps running, and
# the service never has to replace a task.
import time
import unittest

from .helpers import (
    backup_path,
    backup_run,
    create_minimal_compose_dir,
    ensure_empty_dir,
    latest_version_dir,
    require_docker,
    run,
    unique,
    write_databases_csv,
)


def _swarm_state() -> str:
    return run(
        ["docker", "info", "--format", "{{.Swarm.LocalNodeState}}"]
    ).stdout.strip()


def _task_container_id(service: str, timeout_s: int = 60) -> str:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        out = run(
            [
                "docker",
                "ps",
                "--filter",
                f"label=com.docker.swarm.service.name={service}",
                "--format",
                "{{.ID}}",
            ]
        ).stdout.strip()
        if out:
            return out.splitlines()[0]
        time.sleep(2)
    raise RuntimeError(f"No running task container for service {service}")


def _started_at(container_id: str) -> str:
    return run(
        ["docker", "inspect", "--format", "{{.State.StartedAt}}", container_id]
    ).stdout.strip()


class TestE2ESwarmTaskSkip(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-swarm-skip")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)
        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        cls.swarm_initted = False
        if _swarm_state() != "active":
            run(["docker", "swarm", "init", "--advertise-addr", "127.0.0.1"])
            cls.swarm_initted = True

        cls.volume = f"{cls.prefix}-vol"
        cls.service = f"{cls.prefix}-svc"
        cls.volumes = [cls.volume]

        run(["docker", "volume", "create", cls.volume])
        run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{cls.volume}:/data",
                "alpine:3.20",
                "sh",
                "-lc",
                "echo 'swarm-payload' > /data/payload.txt",
            ]
        )

        run(
            [
                "docker",
                "service",
                "create",
                "--name",
                cls.service,
                "--replicas",
                "1",
                "--mount",
                f"type=volume,source={cls.volume},target=/data",
                "alpine:3.20",
                "sleep",
                "3600",
            ]
        )
        cls.task_cid = _task_container_id(cls.service)
        cls.task_started_at = _started_at(cls.task_cid)

        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(cls.databases_csv, [])

        # Whitelist that matches nothing: on main this forces a stop of every
        # container at the volume, i.e. exactly the flake; on this branch the
        # swarm task must be skipped instead. (An empty list would leave the
        # --images-no-stop-required flag without arguments and argparse-fail.)
        backup_run(
            backups_dir=cls.backups_dir,
            repo_name=cls.repo_name,
            compose_dir=cls.compose_dir,
            databases_csv=cls.databases_csv,
            database_containers=["dummy-db"],
            images_no_stop_required=["image-that-matches-nothing"],
        )
        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

    @classmethod
    def tearDownClass(cls) -> None:
        run(["docker", "service", "rm", cls.service], check=False)
        deadline = time.time() + 30
        while time.time() < deadline:
            out = run(
                [
                    "docker",
                    "ps",
                    "-aq",
                    "--filter",
                    f"label=com.docker.swarm.service.name={cls.service}",
                ],
                check=False,
            ).stdout.strip()
            if not out:
                break
            time.sleep(2)
        for v in cls.volumes:
            run(["docker", "volume", "rm", "-f", v], check=False)
        if cls.swarm_initted:
            run(["docker", "swarm", "leave", "--force"], check=False)

    def test_volume_backed_up_hot(self) -> None:
        p = (
            backup_path(
                self.backups_dir,
                self.repo_name,
                self.version,
                self.volume,
            )
            / "files"
            / "payload.txt"
        )
        self.assertTrue(p.is_file(), f"Expected backed up file at: {p}")

    def test_task_container_never_stopped(self) -> None:
        out = run(
            ["docker", "ps", "-q", "--no-trunc", "--filter", f"id={self.task_cid}"]
        ).stdout.strip()
        self.assertTrue(
            out.startswith(self.task_cid) or self.task_cid.startswith(out.strip()[:12]),
            f"Task container {self.task_cid} is no longer running",
        )
        self.assertEqual(
            self.task_started_at,
            _started_at(self.task_cid),
            "Task container was restarted during the backup",
        )

    def test_service_never_replaced_the_task(self) -> None:
        states = run(
            [
                "docker",
                "service",
                "ps",
                self.service,
                "--format",
                "{{.DesiredState}} {{.CurrentState}}",
            ]
        ).stdout.strip()
        lines = [line for line in states.splitlines() if line.strip()]
        self.assertEqual(
            len(lines), 1, f"Service task history shows replacements:\n{states}"
        )
        self.assertIn("Running", lines[0])


if __name__ == "__main__":
    unittest.main()
