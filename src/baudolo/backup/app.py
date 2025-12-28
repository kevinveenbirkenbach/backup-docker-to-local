from __future__ import annotations

import os
import pathlib
from datetime import datetime

import pandas
from dirval import create_stamp_file

from .cli import parse_args
from .compose import handle_docker_compose_services
from .db import backup_database
from .docker import (
    change_containers_status,
    containers_using_volume,
    docker_volume_names,
    get_image_info,
    has_image,
)
from .shell import execute_shell_command
from .volume import backup_volume


def get_machine_id() -> str:
    return execute_shell_command("sha256sum /etc/machine-id")[0][0:64]


def stamp_directory(version_dir: str) -> None:
    """
    Use dirval as a Python library to stamp the directory (no CLI dependency).
    """
    create_stamp_file(version_dir)


def create_version_directory(versions_dir: str, backup_time: str) -> str:
    version_dir = os.path.join(versions_dir, backup_time)
    pathlib.Path(version_dir).mkdir(parents=True, exist_ok=True)
    return version_dir


def create_volume_directory(version_dir: str, volume_name: str) -> str:
    path = os.path.join(version_dir, volume_name)
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)
    return path


def is_image_ignored(container: str, images_no_backup_required: list[str]) -> bool:
    if not images_no_backup_required:
        return False
    img = get_image_info(container)
    return any(pat in img for pat in images_no_backup_required)


def volume_is_fully_ignored(
    containers: list[str], images_no_backup_required: list[str]
) -> bool:
    """
    Skip file backup only if all containers linked to the volume are ignored.
    """
    if not containers:
        return False
    return all(is_image_ignored(c, images_no_backup_required) for c in containers)


def requires_stop(containers: list[str], images_no_stop_required: list[str]) -> bool:
    """
    Stop is required if ANY container image is NOT in the whitelist patterns.
    """
    for c in containers:
        img = get_image_info(c)
        if not any(pat in img for pat in images_no_stop_required):
            return True
    return False


def backup_mariadb_or_postgres(
    *,
    container: str,
    volume_dir: str,
    databases_df: "pandas.DataFrame",
    database_containers: list[str],
) -> bool:
    """
    Returns True if the container is a DB container we handled.
    """
    for img in ["mariadb", "postgres"]:
        if has_image(container, img):
            backup_database(
                container=container,
                volume_dir=volume_dir,
                db_type=img,
                databases_df=databases_df,
                database_containers=database_containers,
            )
            return True
    return False


def _backup_dumps_for_volume(
    *,
    containers: list[str],
    vol_dir: str,
    databases_df: "pandas.DataFrame",
    database_containers: list[str],
) -> bool:
    """
    Create DB dumps for any mariadb/postgres containers attached to this volume.
    Returns True if at least one dump was produced.
    """
    dumped_any = False
    for c in containers:
        if backup_mariadb_or_postgres(
            container=c,
            volume_dir=vol_dir,
            databases_df=databases_df,
            database_containers=database_containers,
        ):
            dumped_any = True
    return dumped_any


def main() -> int:
    args = parse_args()

    machine_id = get_machine_id()
    backup_time = datetime.now().strftime("%Y%m%d%H%M%S")

    versions_dir = os.path.join(args.backups_dir, machine_id, args.repo_name)
    version_dir = create_version_directory(versions_dir, backup_time)

    databases_df = pandas.read_csv(args.databases_csv, sep=";")

    print("💾 Start volume backups...", flush=True)

    for volume_name in docker_volume_names():
        print(f"Start backup routine for volume: {volume_name}", flush=True)
        containers = containers_using_volume(volume_name)

        vol_dir = create_volume_directory(version_dir, volume_name)

        # Old behavior: DB dumps are additional to file backups.
        _backup_dumps_for_volume(
            containers=containers,
            vol_dir=vol_dir,
            databases_df=databases_df,
            database_containers=args.database_containers,
        )

        # dump-only: skip ALL file rsync backups
        if args.dump_only:
            continue

        # skip file backup if all linked containers are ignored
        if volume_is_fully_ignored(containers, args.images_no_backup_required):
            print(
                f"Skipping file backup for volume '{volume_name}' (all linked containers are ignored).",
                flush=True,
            )
            continue

        if args.everything:
            # "everything": always do pre-rsync, then stop + rsync again
            backup_volume(versions_dir, volume_name, vol_dir)
            change_containers_status(containers, "stop")
            backup_volume(versions_dir, volume_name, vol_dir)
            if not args.shutdown:
                change_containers_status(containers, "start")
            continue

        # default: rsync, and if needed stop + rsync
        backup_volume(versions_dir, volume_name, vol_dir)
        if requires_stop(containers, args.images_no_stop_required):
            change_containers_status(containers, "stop")
            backup_volume(versions_dir, volume_name, vol_dir)
            if not args.shutdown:
                change_containers_status(containers, "start")

    # Stamp the backup version directory using dirval (python lib)
    stamp_directory(version_dir)
    print("Finished volume backups.", flush=True)

    print("Handling Docker Compose services...", flush=True)
    handle_docker_compose_services(
        args.compose_dir, args.docker_compose_hard_restart_required
    )

    return 0
