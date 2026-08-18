from __future__ import annotations

from typing import TYPE_CHECKING

from .shell import BackupError, execute_shell_command

if TYPE_CHECKING:
    from collections.abc import Sequence


def docker_exec_argv(
    container: str,
    argv: Sequence[str],
    *,
    interactive: bool = False,
    forward_env: Sequence[str] = (),
) -> list[str]:
    """The argv that runs *argv* inside *container*.

    Args:
        container: the container to run in.
        argv: the command, already split.
        interactive: keep stdin open, for a command that is fed a dump.
        forward_env: names of environment variables to hand to the container.
            Passed as bare ``-e NAME``, so docker copies the value out of this
            process's own environment; spelling ``-e NAME=value`` instead would
            publish a secret in the host's process list.

    Returns:
        The argv list.
    """
    forwarded = [arg for name in forward_env for arg in ("-e", name)]
    return [
        "docker",
        "exec",
        *(["-i"] if interactive else []),
        *forwarded,
        container,
        *argv,
    ]


def get_image_info(container: str) -> str:
    return execute_shell_command(
        ["docker", "inspect", "--format", "{{.Config.Image}}", container]
    )[0]


def image_id(container: str) -> str:
    """The container's image ID, identical for every replica of one image."""
    return execute_shell_command(
        ["docker", "inspect", "--format", "{{.Image}}", container]
    )[0].strip()


def has_tool(container: str, tool: str) -> bool:
    """Whether *tool* runs inside the container.

    Executes the binary rather than asking a shell for it: a distroless image
    has no shell, and `sh -c 'command -v'` would answer "absent" for every
    tool it ships.
    """
    try:
        execute_shell_command(docker_exec_argv(container, [tool, "--version"]))
    except BackupError:
        return False
    return True


def docker_volume_names() -> list[str]:
    return execute_shell_command(["docker", "volume", "ls", "--format", "{{.Name}}"])


def containers_using_volume(volume_name: str) -> list[str]:
    return execute_shell_command(
        [
            "docker",
            "ps",
            "--filter",
            f"volume={volume_name}",
            "--format",
            "{{.Names}}",
        ]
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
            [
                "docker",
                "inspect",
                "--format",
                '{{index .Config.Labels "com.docker.swarm.task.id"}}',
                container,
            ]
        )
    except BackupError:
        still_listed = execute_shell_command(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name=^{container}$",
                "--format",
                "{{.Names}}",
            ]
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
    print(f"{status.capitalize()} containers: {' '.join(containers)}...", flush=True)
    execute_shell_command(["docker", status, *containers])
