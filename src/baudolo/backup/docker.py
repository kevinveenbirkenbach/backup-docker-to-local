from __future__ import annotations

from .shell import BackupException, execute_shell_command


def get_image_info(container: str) -> str:
    return execute_shell_command(
        f"docker inspect --format '{{{{.Config.Image}}}}' {container}"
    )[0]


def has_image(container: str, pattern: str) -> bool:
    """Return True if container's image contains the pattern."""
    return pattern in get_image_info(container)


def docker_volume_names() -> list[str]:
    return execute_shell_command("docker volume ls --format '{{.Name}}'")


def containers_using_volume(volume_name: str) -> list[str]:
    return execute_shell_command(
        f"docker ps --filter volume=\"{volume_name}\" --format '{{{{.Names}}}}'"
    )


def is_swarm_task(container: str) -> bool:
    """Swarm-managed task containers must never be stopped or started
    manually: the orchestrator replaces the stopped task and a later
    `docker start` fails on the detached overlay network. A container that
    vanished between listing and inspect (--rm one-shots, task-history GC)
    counts as not stoppable instead of aborting the whole backup run; if the
    container still exists the inspect failure re-raises, so a broken daemon
    keeps failing the run loudly instead of silently skipping the stop."""
    try:
        out = execute_shell_command(
            "docker inspect --format "
            f"'{{{{index .Config.Labels \"com.docker.swarm.task.id\"}}}}' {container}"
        )
    except BackupException:
        still_listed = execute_shell_command(
            f"docker ps -a --filter name=^{container}$ --format '{{{{.Names}}}}'"
        )
        if still_listed and still_listed[0].strip():
            raise
        return True
    return bool(out and out[0].strip())


def filter_stoppable(containers: list[str]) -> list[str]:
    """Containers baudolo may stop/start itself (everything but swarm tasks)."""
    stoppable = []
    for container in containers:
        if is_swarm_task(container):
            print(
                f"Skipping stop/start for swarm task container '{container}'.",
                flush=True,
            )
            continue
        stoppable.append(container)
    return stoppable


def change_containers_status(containers: list[str], status: str) -> None:
    """Stop or start a list of containers."""
    if not containers:
        print(f"No containers to {status}.", flush=True)
        return
    names = " ".join(containers)
    print(f"{status.capitalize()} containers: {names}...", flush=True)
    execute_shell_command(f"docker {status} {names}")


def docker_volume_exists(volume: str) -> bool:
    # Avoid throwing exceptions for exists checks.
    try:
        execute_shell_command(
            f"docker volume inspect {volume} >/dev/null 2>&1 && echo OK"
        )
        return True
    except Exception:
        return False
