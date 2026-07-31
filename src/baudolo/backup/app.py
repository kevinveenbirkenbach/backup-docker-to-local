"""Back up every Docker volume of a host into a timestamped generation."""

from __future__ import annotations

import os
from contextlib import ExitStack
from datetime import datetime

from .cli import parse_args
from .compose import handle_docker_compose_services
from .docker import (
    change_containers_status,
    containers_using_volume,
    docker_volume_names,
    filter_stoppable,
)
from .dumps import backup_dumps_for_volume, load_databases_df
from .layout import (
    create_version_directory,
    create_volume_directory,
    get_machine_id,
    stamp_directory,
)
from .policy import requires_stop, volume_is_fully_ignored
from .snapshot import volume_snapshot
from .volume import backup_volume, get_storage_path


def main() -> int:
    args = parse_args()

    machine_id = get_machine_id()
    backup_time = datetime.now().strftime("%Y%m%d%H%M%S")

    versions_dir = os.path.join(args.backups_dir, machine_id, args.repo_name)
    version_dir = create_version_directory(versions_dir, backup_time)

    # IMPORTANT:
    # - keep_default_na=False prevents empty fields from turning into NaN
    # - dtype=str keeps all columns stable for comparisons/validation
    #
    # Robust behavior:
    # - if the file is missing or empty, we continue without DB dumps.
    databases_df = load_databases_df(args.databases_csv)

    print("💾 Start volume backups...", flush=True)

    with ExitStack() as stack:
        resolve_source = None
        if args.snapshot:
            resolve_source = stack.enter_context(
                volume_snapshot(args.snapshot, args.snapshot_subject, backup_time)
            )

        for volume_name in docker_volume_names():
            print(f"Start backup routine for volume: {volume_name}", flush=True)
            containers = containers_using_volume(volume_name)

            if volume_is_fully_ignored(containers, args.images_no_backup_required):
                print(
                    f"Skipping volume '{volume_name}' entirely (all linked containers are ignored).",
                    flush=True,
                )
                continue

            vol_dir = create_volume_directory(version_dir, volume_name)

            found_db, dumped_any = backup_dumps_for_volume(
                containers=containers,
                vol_dir=vol_dir,
                databases_df=databases_df,
                database_containers=args.database_containers,
            )

            if args.dump_only_sql:
                if found_db:
                    if not dumped_any:
                        print(
                            f"WARNING: dump-only-sql requested but no DB dump was produced for DB volume '{volume_name}'. "
                            "Falling back to file backup.",
                            flush=True,
                        )
                    else:
                        continue

            live_source = get_storage_path(volume_name)

            def copy(*, authoritative: bool, source: str = live_source) -> None:
                backup_volume(
                    versions_dir,
                    volume_name,
                    vol_dir,
                    authoritative=authoritative,
                    source=source,
                )

            if resolve_source is not None:
                snapshot_source = resolve_source(live_source)
                if os.path.isdir(snapshot_source):
                    copy(authoritative=True, source=snapshot_source)
                else:
                    print(
                        f"WARNING: volume '{volume_name}' is not in the snapshot "
                        "(created after it was taken); copying it live instead.",
                        flush=True,
                    )
                    copy(authoritative=False)
                continue

            if args.everything:
                stoppable = filter_stoppable(containers)
                copy(authoritative=False)
                change_containers_status(stoppable, "stop")
                copy(authoritative=True)
                if not args.shutdown:
                    change_containers_status(stoppable, "start")
                continue

            copy(authoritative=False)
            if requires_stop(containers, args.images_no_stop_required):
                stoppable = filter_stoppable(containers)
                change_containers_status(stoppable, "stop")
                copy(authoritative=True)
                if not args.shutdown:
                    change_containers_status(stoppable, "start")

    stamp_directory(version_dir)
    print("Finished volume backups.", flush=True)

    print("Handling Docker Compose services...", flush=True)
    handle_docker_compose_services(args.compose_dir, args.hard_restart_projects)

    return 0
