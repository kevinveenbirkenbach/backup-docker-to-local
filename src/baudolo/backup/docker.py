from __future__ import annotations

from .shell import execute_shell_command


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
