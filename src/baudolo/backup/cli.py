from __future__ import annotations

import argparse
import os


def parse_args() -> argparse.Namespace:
    dirname = os.path.dirname(__file__)
    default_databases_csv = os.path.join(dirname, "databases.csv")

    p = argparse.ArgumentParser(description="Backup Docker volumes.")

    p.add_argument(
        "--compose-dir",
        type=str,
        required=True,
        help="Path to the parent directory containing docker-compose setups",
    )
    p.add_argument(
        "--docker-compose-hard-restart-required",
        nargs="+",
        default=["mailu"],
        help="Compose dir names that require 'docker-compose down && up -d' (default: mailu)",
    )

    p.add_argument(
        "--repo-name",
        default="backup-docker-to-local",
        help="Backup repo folder name under <backups-dir>/<machine-id>/ (default: git repo folder name)",
    )
    p.add_argument(
        "--databases-csv",
        default=default_databases_csv,
        help=f"Path to databases.csv (default: {default_databases_csv})",
    )
    p.add_argument(
        "--backups-dir",
        default="/var/lib/backup/",
        help="Backup root directory (default: /var/lib/backup/)",
    )

    p.add_argument(
        "--database-containers",
        nargs="+",
        required=True,
        help="Container names treated as special instances for database backups",
    )
    p.add_argument(
        "--images-no-stop-required",
        nargs="+",
        required=True,
        help="Image name patterns for which containers should not be stopped during file backup",
    )
    p.add_argument(
        "--images-no-backup-required",
        nargs="+",
        default=[],
        help="Image name patterns for which no backup should be performed",
    )

    p.add_argument(
        "--everything",
        action="store_true",
        help="Force file backup for all volumes and also execute database dumps (like old script)",
    )
    p.add_argument(
        "--shutdown",
        action="store_true",
        help="Do not restart containers after backup",
    )
    
    p.add_argument(
        "--dump-only-sql",
        action="store_true",
        help=(
            "Create database dumps only for DB volumes. "
            "File backups are skipped for DB volumes if a dump succeeds, "
            "but non-DB volumes are still backed up. "
            "If a DB dump cannot be produced, baudolo falls back to a file backup."
        ),
    )
    return p.parse_args()
