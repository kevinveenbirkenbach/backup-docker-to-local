#!/bin/python
# Backups volumes of running containers

import subprocess
import os
import re
import pathlib
import pandas
from datetime import datetime
import argparse

class BackupException(Exception):
    """Generic exception for backup errors."""
    pass

def execute_shell_command(command):
    """Execute a shell command and return its output."""
    print(command)
    process = subprocess.Popen(
        [command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True
    )
    out, err = process.communicate()
    if process.returncode != 0:
        raise BackupException(
            f"Error in command: {command}\n"
            f"Output: {out}\nError: {err}\n"
            f"Exit code: {process.returncode}"
        )
    return [line.decode("utf-8") for line in out.splitlines()]

def create_version_directory():
    """Create necessary directories for backup."""
    version_dir = os.path.join(VERSIONS_DIR, BACKUP_TIME)
    pathlib.Path(version_dir).mkdir(parents=True, exist_ok=True)
    return version_dir

def get_machine_id():
    """Get the machine identifier."""
    return execute_shell_command("sha256sum /etc/machine-id")[0][0:64]

### GLOBAL CONFIGURATION ###

# Container names treated as special instances for database backups
DATABASE_CONTAINERS = ['central-mariadb', 'central-postgres']

# Images which do not require container stop for file backups
IMAGES_NO_STOP_REQUIRED = []

# Images to skip entirely
IMAGES_NO_BACKUP_REQUIRED = []

# Compose dirs requiring hard restart
DOCKER_COMPOSE_HARD_RESTART_REQUIRED = ['mailu']

# DEFINE CONSTANTS
DIRNAME             = os.path.dirname(__file__)
SCRIPTS_DIRECTORY   = pathlib.Path(os.path.realpath(__file__)).parent.parent
DATABASES           = pandas.read_csv(os.path.join(DIRNAME, "databases.csv"), sep=";")
REPOSITORY_NAME     = os.path.basename(DIRNAME)
MACHINE_ID          = get_machine_id()
BACKUPS_DIR         = '/Backups/'
VERSIONS_DIR        = os.path.join(BACKUPS_DIR, MACHINE_ID, REPOSITORY_NAME)
BACKUP_TIME         = datetime.now().strftime("%Y%m%d%H%M%S")
VERSION_DIR         = create_version_directory()

def get_instance(container):
    """Extract the database instance name based on container name."""
    if container in DATABASE_CONTAINERS:
        instance_name = container
    else:
        instance_name = re.split("(_|-)(database|db|postgres)", container)[0]
    print(f"Extracted instance name: {instance_name}")
    return instance_name

def stamp_directory():
    """Stamp a directory using directory-validator."""
    stamp_command = (
        f"python {SCRIPTS_DIRECTORY}/directory-validator/"
        f"directory-validator.py --stamp {VERSION_DIR}"
    )
    try:
        execute_shell_command(stamp_command)
        print(f"Successfully stamped directory: {VERSION_DIR}")
    except BackupException as e:
        print(f"Error stamping directory {VERSION_DIR}: {e}")
        exit(1)

def backup_database(container, volume_dir, db_type):
    """Backup database (MariaDB or PostgreSQL) if applicable."""
    print(f"Starting database backup for {container} using {db_type}...")
    instance_name = get_instance(container)
    database_entries = DATABASES.loc[DATABASES['instance'] == instance_name]
    if database_entries.empty:
        raise BackupException(f"No entry found for instance '{instance_name}'")
    for database_entry in database_entries.iloc:
        database_name     = database_entry['database']
        database_username = database_entry['username']
        database_password = database_entry['password']
        backup_destination_dir = os.path.join(volume_dir, "sql")
        pathlib.Path(backup_destination_dir).mkdir(parents=True, exist_ok=True)
        backup_destination_file = os.path.join(
            backup_destination_dir,
            f"{database_name}.backup.sql"
        )
        if db_type == 'mariadb':
            cmd = (
                f"docker exec {container} "
                f"/usr/bin/mariadb-dump -u {database_username} "
                f"-p{database_password} {database_name} > {backup_destination_file}"
            )
            execute_shell_command(cmd)
        if db_type == 'postgres':
            cluster_file = os.path.join(
                backup_destination_dir,
                f"{instance_name}.cluster.backup.sql"
            )
            if not database_name:
                fallback_pg_dumpall(
                    container,
                    database_username,
                    database_password,
                    cluster_file
                )
                return
            try:
                if database_password:
                    cmd = (
                        f"PGPASSWORD={database_password} docker exec -i {container} "
                        f"pg_dump -U {database_username} -d {database_name} "
                        f"-h localhost > {backup_destination_file}"
                    )
                else:
                    cmd = (
                        f"docker exec -i {container} pg_dump -U {database_username} "
                        f"-d {database_name} -h localhost --no-password "
                        f"> {backup_destination_file}"
                    )
                execute_shell_command(cmd)
            except BackupException as e:
                print(f"pg_dump failed: {e}")
                print(f"Falling back to pg_dumpall for instance '{instance_name}'")
                fallback_pg_dumpall(
                    container,
                    database_username,
                    database_password,
                    cluster_file
                )
        print(f"Database backup for database {container} completed.")

def get_last_backup_dir(volume_name, current_backup_dir):
    """Get the most recent backup directory for the specified volume."""
    versions = sorted(os.listdir(VERSIONS_DIR), reverse=True)
    for version in versions:
        backup_dir = os.path.join(
            VERSIONS_DIR, version, volume_name, "files", ""
        )
        if backup_dir != current_backup_dir and os.path.isdir(backup_dir):
            return backup_dir
    print(f"No previous backups available for volume: {volume_name}")
    return None

def getStoragePath(volume_name):
    path = execute_shell_command(
        f"docker volume inspect --format '{{{{ .Mountpoint }}}}' {volume_name}"
    )[0]
    return f"{path}/"

def getFileRsyncDestinationPath(volume_dir):
    path = os.path.join(volume_dir, "files")
    return f"{path}/"

def fallback_pg_dumpall(container, username, password, backup_destination_file):
    """Fallback function to run pg_dumpall if pg_dump fails or no DB is defined."""
    print(f"Running pg_dumpall for container '{container}'...")
    cmd = (
        f"PGPASSWORD={password} docker exec -i {container} "
        f"pg_dumpall -U {username} -h localhost > {backup_destination_file}"
    )
    execute_shell_command(cmd)

def backup_volume(volume_name, volume_dir):
    """Perform incremental file backup of a Docker volume."""
    try:
        print(f"Starting backup routine for volume: {volume_name}")
        dest = getFileRsyncDestinationPath(volume_dir)
        pathlib.Path(dest).mkdir(parents=True, exist_ok=True)
        last = get_last_backup_dir(volume_name, dest)
        link_dest = f"--link-dest='{last}'" if last else ""
        source = getStoragePath(volume_name)
        cmd = (
            f"rsync -abP --delete --delete-excluded "
            f"{link_dest} {source} {dest}"
        )
        execute_shell_command(cmd)
    except BackupException as e:
        if "file has vanished" in str(e):
            print("Warning: Some files vanished before transfer. Continuing.")
        else:
            raise
    print(f"Backup routine for volume: {volume_name} completed.")

def get_image_info(container):
    return execute_shell_command(
        f"docker inspect --format '{{{{.Config.Image}}}}' {container}"
    )

def has_image(container, image):
    """Check if the container is using the image"""
    info = get_image_info(container)[0]
    return image in info

def change_containers_status(containers, status):
    """Stop or start a list of containers."""
    if containers:
        names = ' '.join(containers)
        print(f"{status.capitalize()} containers: {names}...")
        execute_shell_command(f"docker {status} {names}")
    else:
        print(f"No containers to {status}.")

def is_image_whitelisted(container, images):
    """
    Return True if the container's image matches any of the whitelist patterns.
    Also prints out the image name and the match result.
    """
    # fetch the image (e.g. "nextcloud:23-fpm-alpine")
    info = get_image_info(container)[0]

    # check against each pattern
    whitelisted = any(pattern in info for pattern in images)

    # log the result
    print(f"Container {container!r} → image {info!r} → whitelisted? {whitelisted}")

    return whitelisted

def is_container_stop_required(containers):
    """
    Check if any of the containers are using images that are not whitelisted.
    If so, print them out and return True; otherwise return False.
    """
    # Find all containers whose image isn’t on the whitelist
    not_whitelisted = [
        c for c in containers
        if not is_image_whitelisted(c, IMAGES_NO_STOP_REQUIRED)
    ]

    if not_whitelisted:
        print(f"Containers requiring stop because they are not whitelisted: {', '.join(not_whitelisted)}")
        return True

    return False

def create_volume_directory(volume_name):
    """Create necessary directories for backup."""
    path = os.path.join(VERSION_DIR, volume_name)
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)
    return path

def is_image_ignored(container):
    """Check if the container's image is one of the ignored images."""
    return any(has_image(container, img) for img in IMAGES_NO_BACKUP_REQUIRED)

def backup_with_containers_paused(volume_name, volume_dir, containers, shutdown):
    change_containers_status(containers, 'stop')
    backup_volume(volume_name, volume_dir)
    if not shutdown:
        change_containers_status(containers, 'start')

def backup_mariadb_or_postgres(container, volume_dir):
    """Performs database image specific backup procedures"""
    for img in ['mariadb', 'postgres']:
        if has_image(container, img):
            backup_database(container, volume_dir, img)
            return True
    return False

def default_backup_routine_for_volume(volume_name, containers, shutdown):
    """Perform backup routine for a given volume."""
    vol_dir = ""
    for c in containers:
        if is_image_ignored(c):
            print(f"Ignoring volume '{volume_name}' linked to container '{c}'.")
            continue
        vol_dir = create_volume_directory(volume_name)
        if backup_mariadb_or_postgres(c, vol_dir):
            return
    if vol_dir:
        backup_volume(volume_name, vol_dir)
        if is_container_stop_required(containers):
            backup_with_containers_paused(volume_name, vol_dir, containers, shutdown)

def backup_everything(volume_name, containers, shutdown):
    """Perform file backup routine for a given volume."""
    vol_dir = create_volume_directory(volume_name)
    for c in containers:
        backup_mariadb_or_postgres(c, vol_dir)
    backup_volume(volume_name, vol_dir)
    backup_with_containers_paused(volume_name, vol_dir, containers, shutdown)

def hard_restart_docker_services(dir_path):
    """Perform a hard restart of docker-compose services in the given directory."""
    try:
        print(f"Performing hard restart for docker-compose services in: {dir_path}")
        subprocess.run(["docker-compose", "down"], cwd=dir_path, check=True)
        subprocess.run(["docker-compose", "up", "-d"], cwd=dir_path, check=True)
        print(f"Hard restart completed successfully in: {dir_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error during hard restart in {dir_path}: {e}")
        exit(2)

def handle_docker_compose_services(parent_directory):
    """Iterate through directories and restart or hard restart services as needed."""
    for entry in os.scandir(parent_directory):
        if entry.is_dir():
            dir_path = entry.path
            name = os.path.basename(dir_path)
            print(f"Checking directory: {dir_path}")
            compose_file = os.path.join(dir_path, "docker-compose.yml")
            if os.path.isfile(compose_file):
                print(f"Found docker-compose.yml in {dir_path}.")
                if name in DOCKER_COMPOSE_HARD_RESTART_REQUIRED:
                    print(f"Directory {name} detected. Performing hard restart...")
                    hard_restart_docker_services(dir_path)
                else:
                    print(f"No restart required for services in {dir_path}...")
            else:
                print(f"No docker-compose.yml found in {dir_path}. Skipping.")

def main():
    global DATABASE_CONTAINERS, IMAGES_NO_STOP_REQUIRED
    parser = argparse.ArgumentParser(description='Backup Docker volumes.')
    parser.add_argument('--everything', action='store_true',
                        help='Force file backup for all volumes and additional execute database dumps')
    parser.add_argument('--shutdown', action='store_true',
                        help='Doesn\'t restart containers after backup')
    parser.add_argument('--compose-dir', type=str, required=True,
                        help='Path to the parent directory containing docker-compose setups')
    parser.add_argument(
        '--database-containers',
        nargs='+',
        required=True,
        help='List of container names treated as special instances for database backups'
    )
    parser.add_argument(
        '--images-no-stop-required',
        nargs='+',
        required=True,
        help='List of image names for which containers should not be stopped during file backup'
    )
    parser.add_argument(
        '--images-no-backup-required',
        nargs='+',
        help='List of image names for which no backup should be performed (optional)'
    )
    args = parser.parse_args()
    DATABASE_CONTAINERS = args.database_containers
    IMAGES_NO_STOP_REQUIRED = args.images_no_stop_required
    if args.images_no_backup_required is not None:
        global IMAGES_NO_BACKUP_REQUIRED
        IMAGES_NO_BACKUP_REQUIRED = args.images_no_backup_required

    print('Start volume backups...')
    volume_names = execute_shell_command("docker volume ls --format '{{.Name}}'")
    for volume_name in volume_names:
        print(f'Start backup routine for volume: {volume_name}')
        containers = execute_shell_command(
            f"docker ps --filter volume=\"{volume_name}\" --format '{{{{.Names}}}}'"
        )
        if args.everything:
            backup_everything(volume_name, containers, args.shutdown)
        else:
            default_backup_routine_for_volume(volume_name, containers, args.shutdown)

    stamp_directory()
    print('Finished volume backups.')

    print('Handling Docker Compose services...')
    handle_docker_compose_services(args.compose_dir)

if __name__ == "__main__":
    main()
