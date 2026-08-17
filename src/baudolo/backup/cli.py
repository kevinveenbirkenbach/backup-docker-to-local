from __future__ import annotations

import argparse


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backup Docker volumes.")

    p.add_argument(
        "--compose-dir",
        type=str,
        required=True,
        help="Path to the parent directory containing docker-compose setups",
    )
    p.add_argument(
        "--hard-restart-projects",
        nargs="*",
        default=[],
        help="Compose dir names that require 'docker-compose down && up -d' (default: none; pass e.g. 'mailu' under compose where the DB cannot be backed up hot)",
    )

    p.add_argument(
        "--repo-name",
        required=True,
        help="Backup repo folder name under <backups-dir>/<machine-id>/",
    )
    p.add_argument(
        "--databases-csv",
        help="Path to databases.csv; required unless --only-files is given",
    )
    p.add_argument(
        "--backups-dir",
        required=True,
        help="Backup root directory (e.g. /var/lib/backup/)",
    )

    p.add_argument(
        "--snapshot",
        choices=["btrfs", "zfs"],
        help="Capture every volume from one atomic filesystem snapshot instead of copying the live tree. Containers are not stopped, and the copy is a single pass. Requires --snapshot-subject. Omit to keep the live two-pass copy.",
    )
    p.add_argument(
        "--snapshot-subject",
        help="Btrfs subvolume or zfs dataset mountpoint holding the docker volumes, e.g. /var/lib/docker. Required with --snapshot.",
    )

    p.add_argument(
        "--database-containers",
        nargs="+",
        default=[],
        help="Container names treated as special instances for database backups",
    )
    p.add_argument(
        "--images-no-stop-required",
        nargs="+",
        default=[],
        help="Exact image references (repo:tag, incl. any registry prefix) whose containers must not be stopped during file backup",
    )
    p.add_argument(
        "--images-no-backup-required",
        nargs="+",
        default=[],
        help="Exact image references (repo:tag, incl. any registry prefix) for which no backup should be performed",
    )

    p.add_argument(
        "--volumes-no-backup-required",
        nargs="+",
        default=[],
        help="Exact volume names that are never backed up, whatever containers use them. For derived trees a restore cannot reproduce, above all a nested docker data root",
    )

    p.add_argument(
        "--shutdown",
        action="store_true",
        help="Do not restart containers after backup",
    )

    scope = p.add_mutually_exclusive_group()
    scope.add_argument(
        "--only-sql",
        action="store_true",
        help=(
            "Create database dumps only for DB volumes. "
            "File backups are skipped for DB volumes if a dump succeeds, "
            "but non-DB volumes are still backed up. "
            "If a DB dump cannot be produced, baudolo falls back to a file backup."
        ),
    )
    scope.add_argument(
        "--only-files",
        action="store_true",
        help=(
            "Take no database dumps at all and back up every volume as files. "
            "For hosts that hold no database credentials. A database's files "
            "are only consistent if its containers are stopped for the second "
            "pass, so keep its image off --images-no-stop-required."
        ),
    )
    args = p.parse_args()
    if not args.only_files and not args.databases_csv:
        p.error("--databases-csv is required unless --only-files is given")
    if bool(args.snapshot) != bool(args.snapshot_subject):
        p.error("--snapshot and --snapshot-subject must be given together")
    if args.snapshot and args.shutdown:
        p.error(
            "--shutdown is meaningless with --snapshot: containers are never stopped"
        )
    if args.snapshot and args.hard_restart_projects:
        p.error(
            "--hard-restart-projects is meaningless with --snapshot: the flag exists "
            "for stacks whose database cannot be backed up hot, which a snapshot solves"
        )
    return args
