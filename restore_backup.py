#!/usr/bin/env python3
# @todo Not tested yet. Needs to be tested
"""
restore_backup.py

A script to recover Docker volumes and database dumps from local backups.
Supports an --empty flag to clear the database objects before import (drops all tables/functions etc.).
"""
import argparse
import os
import sys
import subprocess


def run_command(cmd, capture_output=False, input=None, **kwargs):
    """Run a subprocess command and handle errors."""
    try:
        result = subprocess.run(cmd, check=True, capture_output=capture_output, input=input, **kwargs)
        return result
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Command '{' '.join(cmd)}' failed with exit code {e.returncode}")
        if e.stdout:
            print(e.stdout.decode())
        if e.stderr:
            print(e.stderr.decode())
        sys.exit(1)


def recover_postgres(container, password, db_name, user, backup_sql, empty=False):
    print("Recovering PostgreSQL dump...")
    os.environ['PGPASSWORD'] = password
    if empty:
        print("Dropping existing PostgreSQL objects...")
        # Drop all tables, views, sequences, functions in public schema
        drop_sql = """
DO $$ DECLARE r RECORD;
BEGIN
  FOR r IN (
    SELECT table_name AS name, 'TABLE' AS type FROM information_schema.tables WHERE table_schema='public'
    UNION ALL
    SELECT routine_name AS name, 'FUNCTION' AS type FROM information_schema.routines WHERE specific_schema='public'
    UNION ALL
    SELECT sequence_name AS name, 'SEQUENCE' AS type FROM information_schema.sequences WHERE sequence_schema='public'
  ) LOOP
    -- Use %s for type to avoid quoting the SQL keyword
    EXECUTE format('DROP %s public.%I CASCADE', r.type, r.name);
  END LOOP;
END
$$;
"""
        run_command([
            'docker', 'exec', '-i', container,
            'psql', '-v', 'ON_ERROR_STOP=1', '-U', user, '-d', db_name
        ], input=drop_sql.encode())
        print("Existing objects dropped.")
    print("Importing the dump...")
    with open(backup_sql, 'rb') as f:
        run_command([
            'docker', 'exec', '-i', container,
            'psql', '-v', 'ON_ERROR_STOP=1', '-U', user, '-d', db_name
        ], stdin=f)
    print("PostgreSQL recovery complete.")


def recover_mariadb(container, password, db_name, user, backup_sql, empty=False):
    print("Recovering MariaDB dump...")
    if empty:
        print("Dropping existing MariaDB tables...")
        # Disable foreign key checks
        run_command([
            'docker', 'exec', container,
            'mysql', '-u', user, f"--password={password}", '-e', 'SET FOREIGN_KEY_CHECKS=0;'
        ])
        # Get all table names
        result = run_command([
            'docker', 'exec', container,
            'mysql', '-u', user, f"--password={password}", '-N', '-e',
            f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{db_name}';"
        ], capture_output=True)
        tables = result.stdout.decode().split()
        for tbl in tables:
            run_command([
                'docker', 'exec', container,
                'mysql', '-u', user, f"--password={password}", '-e',
                f"DROP TABLE IF EXISTS `{db_name}`.`{tbl}`;"
            ])
        # Enable foreign key checks
        run_command([
            'docker', 'exec', container,
            'mysql', '-u', user, f"--password={password}", '-e', 'SET FOREIGN_KEY_CHECKS=1;'
        ])
        print("Existing tables dropped.")
    print("Importing the dump...")
    with open(backup_sql, 'rb') as f:
        run_command([
            'docker', 'exec', '-i', container,
            'mariadb', '-u', user, f"--password={password}", db_name
        ], stdin=f)
    print("MariaDB recovery complete.")


def recover_files(volume_name, backup_files):
    print(f"Inspecting volume {volume_name}...")
    inspect = subprocess.run(['docker', 'volume', 'inspect', volume_name], stdout=subprocess.DEVNULL)
    if inspect.returncode != 0:
        print(f"Volume {volume_name} does not exist. Creating...")
        run_command(['docker', 'volume', 'create', volume_name])
    else:
        print(f"Volume {volume_name} already exists.")

    if not os.path.isdir(backup_files):
        print(f"ERROR: Backup files folder '{backup_files}' does not exist.")
        sys.exit(1)

    print("Recovering files...")
    run_command([
        'docker', 'run', '--rm',
        '-v', f"{volume_name}:/recover/",
        '-v', f"{backup_files}:/backup/",
        'kevinveenbirkenbach/alpine-rsync',
        'sh', '-c', 'rsync -avv --delete /backup/ /recover/'
    ])
    print("File recovery complete.")


def main():
    parser = argparse.ArgumentParser(
        description='Recover Docker volumes and database dumps from local backups.'
    )
    parser.add_argument('volume_name', help='Name of the Docker volume')
    parser.add_argument('backup_hash', help='Hashed Machine ID')
    parser.add_argument('version', help='Version to recover')

    parser.add_argument('--db-type', choices=['postgres', 'mariadb'], help='Type of database backup')
    parser.add_argument('--db-container', help='Docker container name for the database')
    parser.add_argument('--db-password', help='Password for the database user')
    parser.add_argument('--db-name', help='Name of the database')
    parser.add_argument('--empty', action='store_true', help='Drop existing database objects before importing')

    args = parser.parse_args()

    volume = args.volume_name
    backup_hash = args.backup_hash
    version = args.version

    backup_folder = os.path.join('Backups', backup_hash, 'backup-docker-to-local', version, volume)
    backup_files = os.path.join(os.sep, backup_folder, 'files')
    backup_sql = None
    if args.db_name:
        backup_sql = os.path.join(os.sep, backup_folder, 'sql', f"{args.db_name}.backup.sql")

    # Database recovery
    if args.db_type:
        if not (args.db_container and args.db_password and args.db_name):
            print("ERROR: A database backup exists, aber ein Parameter fehlt.")
            sys.exit(1)

        user = args.db_name
        if args.db_type == 'postgres':
            recover_postgres(args.db_container, args.db_password, args.db_name, user, backup_sql, empty=args.empty)
        else:
            recover_mariadb(args.db_container, args.db_password, args.db_name, user, backup_sql, empty=args.empty)
        sys.exit(0)

    # File recovery
    recover_files(volume, backup_files)


if __name__ == '__main__':
    main()
