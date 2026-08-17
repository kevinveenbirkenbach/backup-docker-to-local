from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass, field

from .shell import BackupException, execute_shell_command


@dataclass(frozen=True)
class Backing:
    """Where a docker volume actually keeps its data.

    Args:
        mountpoint: the path the daemon reports.
        driver: the volume driver, ``local`` for the built-in one.
        options: the driver options; a non-empty map means the mountpoint is a
            mount target rather than the storage itself.
    """

    mountpoint: str
    driver: str = "local"
    options: dict = field(default_factory=dict)

    @property
    def source(self) -> str:
        return f"{self.mountpoint}/"


def inspect_backing(volume_name: str) -> Backing:
    reported = execute_shell_command(
        ["docker", "volume", "inspect", "--format", "{{json .}}", volume_name]
    )[0]
    data = json.loads(reported)
    return Backing(
        data.get("Mountpoint") or "",
        data.get("Driver") or "",
        data.get("Options") or {},
    )


def get_last_backup_dir(
    versions_dir: str, volume_name: str, current_backup_dir: str
) -> str | None:
    versions = sorted(os.listdir(versions_dir), reverse=True)
    for version in versions:
        candidate = os.path.join(versions_dir, version, volume_name, "files", "")
        if candidate != current_backup_dir and os.path.isdir(candidate):
            return candidate
    return None


def backup_volume(
    versions_dir: str,
    volume_name: str,
    volume_dir: str,
    *,
    authoritative: bool,
    source: str,
) -> None:
    """Perform incremental file backup of a Docker volume.

    Args:
        authoritative: compare source and destination by content instead of by
            size and whole-second mtime. Required on a pass whose destination was
            already written from a live source, where a file can differ while
            both attributes still agree.
        source: directory to read from - the volume's mountpoint, or its path
            inside a snapshot.
    """
    dest = os.path.join(volume_dir, "files") + "/"
    pathlib.Path(dest).mkdir(parents=True, exist_ok=True)

    last = get_last_backup_dir(versions_dir, volume_name, dest)
    cmd = ["rsync", "-aP", "--no-D", "--delete", "--delete-excluded"]
    if authoritative:
        cmd.append("--checksum")
    if last:
        cmd.append(f"--link-dest={last}")
    cmd += [source, dest]

    try:
        execute_shell_command(cmd)
    except BackupException as e:
        if "file has vanished" in str(e):
            print(
                "Warning: Some files vanished before transfer. Continuing.", flush=True
            )
        else:
            raise
