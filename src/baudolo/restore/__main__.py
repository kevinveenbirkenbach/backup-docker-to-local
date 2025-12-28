from __future__ import annotations

import argparse
import sys

from .paths import BackupPaths
from .files import restore_volume_files
from .db.postgres import restore_postgres_sql
from .db.mariadb import restore_mariadb_sql


def _add_common_backup_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("volume_name", help="Docker volume name (target volume)")
    p.add_argument("backup_hash", help="Hashed machine id")
    p.add_argument("version", help="Backup version directory name")

    p.add_argument(
        "--backups-dir",
        default="/Backups",
        help="Backup root directory (default: /Backups)",
    )
    p.add_argument(
        "--repo-name",
        default="backup-docker-to-local",
        help="Backup repo folder name under <backups-dir>/<hash>/ (default: backup-docker-to-local)",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="baudolo-restore",
        description="Restore docker volume files and DB dumps.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ------------------------------------------------------------------
    # files
    # ------------------------------------------------------------------
    p_files = sub.add_parser("files", help="Restore files into a docker volume")
    _add_common_backup_args(p_files)
    p_files.add_argument(
        "--rsync-image",
        default="ghcr.io/kevinveenbirkenbach/alpine-rsync",
    )
    p_files.add_argument(
        "--source-volume",
        default=None,
        help=(
            "Volume name used as backup source path key. "
            "Defaults to <volume_name> (target volume). "
            "Use this when restoring from one volume backup into a different target volume."
        ),
    )

    # ------------------------------------------------------------------
    # postgres
    # ------------------------------------------------------------------
    p_pg = sub.add_parser("postgres", help="Restore a single PostgreSQL database dump")
    _add_common_backup_args(p_pg)
    p_pg.add_argument("--container", required=True)
    p_pg.add_argument("--db-name", required=True)
    p_pg.add_argument("--db-user", default=None, help="Defaults to db-name if omitted")
    p_pg.add_argument("--db-password", required=True)
    p_pg.add_argument("--empty", action="store_true")

    # ------------------------------------------------------------------
    # mariadb
    # ------------------------------------------------------------------
    p_mdb = sub.add_parser(
        "mariadb", help="Restore a single MariaDB/MySQL-compatible dump"
    )
    _add_common_backup_args(p_mdb)
    p_mdb.add_argument("--container", required=True)
    p_mdb.add_argument("--db-name", required=True)
    p_mdb.add_argument("--db-user", default=None, help="Defaults to db-name if omitted")
    p_mdb.add_argument("--db-password", required=True)
    p_mdb.add_argument("--empty", action="store_true")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "files":
            # target volume = args.volume_name
            # source volume (backup key) defaults to target volume
            source_volume = args.source_volume or args.volume_name

            bp_files = BackupPaths(
                source_volume,
                args.backup_hash,
                args.version,
                repo_name=args.repo_name,
                backups_dir=args.backups_dir,
            )

            return restore_volume_files(
                args.volume_name,
                bp_files.files_dir(),
                rsync_image=args.rsync_image,
            )

        if args.cmd == "postgres":
            user = args.db_user or args.db_name
            restore_postgres_sql(
                container=args.container,
                db_name=args.db_name,
                user=user,
                password=args.db_password,
                sql_path=BackupPaths(
                    args.volume_name,
                    args.backup_hash,
                    args.version,
                    repo_name=args.repo_name,
                    backups_dir=args.backups_dir,
                ).sql_file(args.db_name),
                empty=args.empty,
            )
            return 0

        if args.cmd == "mariadb":
            user = args.db_user or args.db_name
            restore_mariadb_sql(
                container=args.container,
                db_name=args.db_name,
                user=user,
                password=args.db_password,
                sql_path=BackupPaths(
                    args.volume_name,
                    args.backup_hash,
                    args.version,
                    repo_name=args.repo_name,
                    backups_dir=args.backups_dir,
                ).sql_file(args.db_name),
                empty=args.empty,
            )
            return 0

        parser.error("Unhandled command")
        return 2

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
