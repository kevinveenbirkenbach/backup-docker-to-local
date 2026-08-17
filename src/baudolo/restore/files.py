"""Restore a volume's file tree by writing into its mountpoint.

That shortcut only holds for a plain local volume, where the mountpoint *is*
the storage. A volume with driver options - NFS, a bind device, tmpfs - keeps
the same ``/var/lib/docker/volumes/<name>/_data`` path, but docker mounts the
real backing store over it on demand and unmounts it again when the last
consumer stops. Writing there while nothing has it mounted lands in the empty
directory underneath, is hidden by the next mount, and rsync reports success.
"""

from __future__ import annotations

import os
import sys

from .run import docker_volume_exists, run, stdout_of

INSPECT_FORMAT = (
    "{{ .Mountpoint }}|{{ .Driver }}|{{ if .Options }}opts{{ else }}plain{{ end }}"
)


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
        ["docker", "volume", "inspect", "--format", INSPECT_FORMAT, volume_name],
        capture=True,
    )
    fields = stdout_of(cp).split("|")
    mountpoint = fields[0] if fields else ""
    if not mountpoint:
        print(
            f"ERROR: could not resolve mountpoint for volume {volume_name}",
            file=sys.stderr,
        )
        return 2

    driver, options = (fields + ["local", "plain"])[1:3]
    if (driver != "local" or options == "opts") and not os.path.ismount(mountpoint):
        print(
            f"ERROR: volume {volume_name} has a backing store of its own "
            f"(driver {driver}) but nothing has it mounted; writing to "
            f"{mountpoint} now would land under the mount and be lost. "
            "Start a container that mounts the volume, then restore again.",
            file=sys.stderr,
        )
        return 2

    src = os.path.join(backup_files_dir, "")
    dest = os.path.join(mountpoint, "")
    run(["rsync", "-avv", "--delete", src, dest])
    print("File restore complete.")
    return 0
