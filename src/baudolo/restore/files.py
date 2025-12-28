from __future__ import annotations

import os
import sys

from .run import run, docker_volume_exists


def restore_volume_files(
    volume_name: str, backup_files_dir: str, *, rsync_image: str
) -> int:
    if not os.path.isdir(backup_files_dir):
        print(f"ERROR: backup files dir not found: {backup_files_dir}", file=sys.stderr)
        return 2

    if not docker_volume_exists(volume_name):
        print(f"Volume {volume_name} does not exist. Creating...")
        run(["docker", "volume", "create", volume_name])
    else:
        print(f"Volume {volume_name} already exists.")

    # Keep behavior close to the old script: rsync -avv --delete
    run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume_name}:/recover/",
            "-v",
            f"{backup_files_dir}:/backup/",
            rsync_image,
            "sh",
            "-lc",
            "rsync -avv --delete /backup/ /recover/",
        ]
    )
    print("File restore complete.")
    return 0
