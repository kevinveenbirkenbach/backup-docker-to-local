#!/usr/bin/env python3
"""
Restore multiple PostgreSQL databases from .backup.sql files via a Docker container.

Usage:
  ./restore_databases.py /path/to/backup_dir container_name
"""
import argparse
import subprocess
import sys
import os
import glob

def run_command(cmd, stdin=None):
    """
    Run a subprocess command and abort immediately on any failure.
    :param cmd: list of command parts
    :param stdin: file-like object to use as stdin
    """
    subprocess.run(cmd, stdin=stdin, check=True)


def main():
    parser = argparse.ArgumentParser(
        description="Restore Postgres databases from backup SQL files via Docker container."
    )
    parser.add_argument(
        "backup_dir",
        help="Path to directory containing .backup.sql files"
    )
    parser.add_argument(
        "container",
        help="Name of the Postgres Docker container"
    )
    args = parser.parse_args()

    backup_dir = args.backup_dir
    container = args.container

    pattern = os.path.join(backup_dir, "*.backup.sql")
    sql_files = sorted(glob.glob(pattern))
    if not sql_files:
        print(f"No .backup.sql files found in {backup_dir}", file=sys.stderr)
        sys.exit(1)

    for sqlfile in sql_files:
        # Extract database name by stripping the full suffix '.backup.sql'
        filename = os.path.basename(sqlfile)
        if not filename.endswith('.backup.sql'):
            continue
        dbname = filename[:-len('.backup.sql')]
        print(f"=== Processing {sqlfile} → database: {dbname} ===")

        # Drop the database, forcing disconnect of sessions if necessary
        run_command([
            "docker", "exec", "-i", container,
            "psql", "-U", "postgres", "-c",
            f"DROP DATABASE IF EXISTS \"{dbname}\" WITH (FORCE);"
        ])

        # Create a fresh database
        run_command([
            "docker", "exec", "-i", container,
            "psql", "-U", "postgres", "-c",
            f"CREATE DATABASE \"{dbname}\";"
        ])

        # Ensure the ownership role exists
        print(f"Ensuring role '{dbname}' exists...")
        run_command([
            "docker", "exec", "-i", container,
            "psql", "-U", "postgres", "-c",
            (
                "DO $$BEGIN "
                f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{dbname}') THEN "
                f"CREATE ROLE \"{dbname}\"; "
                "END IF; "
                "END$$;"
            )
        ])

        # Restore the dump into the database by streaming file (will abort on first error)
        print(f"Restoring dump into {dbname} (this may take a while)…")
        with open(sqlfile, 'rb') as infile:
            run_command([
                "docker", "exec", "-i", container,
                "psql", "-U", "postgres", "-d", dbname
            ], stdin=infile)

        print(f"✔ {dbname} restored.")

    print("All databases have been restored.")


if __name__ == "__main__":
    main()
