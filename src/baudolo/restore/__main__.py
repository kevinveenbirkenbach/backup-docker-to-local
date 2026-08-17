from __future__ import annotations

import argparse
import sys

from .db.cluster import restore_cluster_sql
from .db.mariadb import restore_mariadb_sql
from .db.postgres import restore_postgres_sql
from .files import restore_volume_files
from .paths import BackupPaths


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
        required=True,
        help="Backup repo folder name under <backups-dir>/<hash>/",
    )


def _add_common_engine_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--container", required=True)
    p.add_argument("--db-password", required=True)
    p.add_argument("--empty", action="store_true")
    p.add_argument(
        "--no-version-check",
        action="store_true",
        help=(
            "Replay even if the dump comes from a newer engine than the target. "
            "With --empty this can leave an emptied database behind."
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="baudolo-restore",
        description="Restore docker volume files and DB dumps.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_files = sub.add_parser("files", help="Restore files into a docker volume")
    _add_common_backup_args(p_files)
    p_files.add_argument(
        "--source-volume",
        default=None,
        help=(
            "Volume name used as backup source path key. "
            "Defaults to <volume_name> (target volume). "
            "Use this when restoring from one volume backup into a different target volume."
        ),
    )

    p_pg = sub.add_parser("postgres", help="Restore a single PostgreSQL database dump")
    _add_common_backup_args(p_pg)
    _add_common_engine_args(p_pg)
    p_pg.add_argument("--db-name", required=True)
    p_pg.add_argument("--db-user", default=None, help="Defaults to db-name if omitted")

    p_cluster = sub.add_parser(
        "cluster", help="Restore a full PostgreSQL cluster dump (pg_dumpall)"
    )
    _add_common_backup_args(p_cluster)
    _add_common_engine_args(p_cluster)
    p_cluster.add_argument(
        "--instance",
        required=True,
        help="Instance the dump was taken from; names <instance>.cluster.backup.sql",
    )
    p_cluster.add_argument(
        "--db-user",
        required=True,
        help="Superuser of the instance; the dump creates roles and databases",
    )

    p_mdb = sub.add_parser(
        "mariadb", help="Restore a single MariaDB/MySQL-compatible dump"
    )
    _add_common_backup_args(p_mdb)
    _add_common_engine_args(p_mdb)
    p_mdb.add_argument("--db-name", required=True)
    p_mdb.add_argument("--db-user", default=None, help="Defaults to db-name if omitted")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "files":
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
                check_version=not args.no_version_check,
            )
            return 0

        if args.cmd == "cluster":
            restore_cluster_sql(
                container=args.container,
                user=args.db_user,
                password=args.db_password,
                sql_path=BackupPaths(
                    args.volume_name,
                    args.backup_hash,
                    args.version,
                    repo_name=args.repo_name,
                    backups_dir=args.backups_dir,
                ).cluster_file(args.instance),
                empty=args.empty,
                check_version=not args.no_version_check,
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
                check_version=not args.no_version_check,
            )
            return 0

        parser.error("Unhandled command")
        return 2

    except Exception as e:  # noqa: BLE001 - CLI boundary: any failure becomes exit 1
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
