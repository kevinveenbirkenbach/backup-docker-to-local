from __future__ import annotations

import os
import pathlib

from .shell import BackupException, execute_shell_command


def get_storage_path(volume_name: str) -> str:
    path = execute_shell_command(
        f"docker volume inspect --format '{{{{ .Mountpoint }}}}' {volume_name}"
    )[0]
    return f"{path}/"


def get_last_backup_dir(
    versions_dir: str, volume_name: str, current_backup_dir: str
) -> str | None:
    versions = sorted(os.listdir(versions_dir), reverse=True)
    for version in versions:
        candidate = os.path.join(versions_dir, version, volume_name, "files", "")
        if candidate != current_backup_dir and os.path.isdir(candidate):
            return candidate
    return None


def backup_volume(versions_dir: str, volume_name: str, volume_dir: str) -> None:
    """Perform incremental file backup of a Docker volume."""
    dest = os.path.join(volume_dir, "files") + "/"
    pathlib.Path(dest).mkdir(parents=True, exist_ok=True)

    last = get_last_backup_dir(versions_dir, volume_name, dest)
    link_dest = f"--link-dest='{last}'" if last else ""
    source = get_storage_path(volume_name)

    cmd = f"rsync -abP --delete --delete-excluded {link_dest} {source} {dest}"

    try:
        execute_shell_command(cmd)
    except BackupException as e:
        if "file has vanished" in str(e):
            print(
                "Warning: Some files vanished before transfer. Continuing.", flush=True
            )
        else:
            raise
