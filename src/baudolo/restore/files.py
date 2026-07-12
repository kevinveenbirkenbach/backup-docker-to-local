from __future__ import annotations

import os
import sys

from .run import docker_volume_exists, run


def restore_volume_files(volume_name: str, backup_files_dir: str) -> int:
    if not os.path.isdir(backup_files_dir):
        print(f"ERROR: backup files dir not found: {backup_files_dir}", file=sys.stderr)
        return 2

    if not docker_volume_exists(volume_name):
        print(f"Volume {volume_name} does not exist. Creating...")
        run(["docker", "volume", "create", volume_name])
    else:
        print(f"Volume {volume_name} already exists.")

    cp = run(
        ["docker", "volume", "inspect", "--format", "{{ .Mountpoint }}", volume_name],
        capture=True,
    )
    raw = cp.stdout or b""
    mountpoint = (raw.decode() if isinstance(raw, bytes) else raw).strip()
    if not mountpoint:
        print(
            f"ERROR: could not resolve mountpoint for volume {volume_name}",
            file=sys.stderr,
        )
        return 2

    src = os.path.join(backup_files_dir, "")
    dest = os.path.join(mountpoint, "")
    run(["rsync", "-avv", "--delete", src, dest])
    print("File restore complete.")
    return 0
