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
    process = subprocess.Popen([command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    out, err = process.communicate()
    if process.returncode != 0:
        raise BackupException(f"Error in command: {command}\nOutput: {out}\nError: {err}\nExit code: {process.returncode}")
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

IMAGES_NO_STOP_REQUIRED = [
    'akaunting',
    'baserow',
    'discourse',
    'element',
    'gitea',
    'listmonk',
    'mastodon',
    'matomo',
    'nextcloud',
    'openproject',
    'peertube',
    'pixelfed',
    'wordpress' 
]

IMAGES_NO_BACKUP_REQUIRED = [
    'redis', 
    'memcached'
    ]

DIRNAME = os.path.dirname(__file__)

DATABASES = pandas.read_csv(os.path.join(DIRNAME, "databases.csv"), sep=";")
REPOSITORY_NAME = os.path.basename(DIRNAME)
MACHINE_ID = get_machine_id()
BACKUPS_DIR = '/Backups/'
VERSIONS_DIR = os.path.join(BACKUPS_DIR, MACHINE_ID, REPOSITORY_NAME)
BACKUP_TIME = datetime.now().strftime("%Y%m%d%H%M%S")
VERSION_DIR = create_version_directory()

def get_instance(container):
    # The function is defined to take one parameter, 'container', 
    # which is expected to be a string.

    # This line uses regular expressions to split the 'container' string.
    # 're.split' is a method that divides a string into a list, based on the occurrences of a pattern.
    instance_name = re.split("(_|-)(database|db|postgres)", container)[0]
    # The pattern "(_|-)(database|db|postgres)" is explained as follows:
    #    - "(_|-)": Matches an underscore '_' or a hyphen '-'.
    #    - "(database|db|postgres)": Matches one of the strings "database", "db", or "postgres".
    # So, this pattern will match segments like "_database", "-db", "_postgres", etc.
    # For example, in "central-db", it matches "-db".

    # After splitting, [0] is used to select the first element of the list resulting from the split.
    # This element is the string portion before the matched pattern.
    # For "central-db", the split results in ["central", "db"], and [0] selects "central".

    print(f"Extracted instance name: {instance_name}")
    return instance_name

def backup_database(container, volume_dir, db_type):
    """Backup database (MariaDB or PostgreSQL) if applicable."""
    print(f"Starting database backup for {container} using {db_type}...")
    instance_name = get_instance(container)

    # Filter the DataFrame for the given instance_name
    database_entries = DATABASES.loc[DATABASES['instance'] == instance_name]

    # Check if there are more than one entries
    if len(database_entries) > 1:
        raise BackupException(f"More than one entry found for instance '{instance_name}'")

    # Check if there is no entry
    if database_entries.empty:
        raise BackupException(f"No entry found for instance '{instance_name}'")

    # Get the first (and only) entry
    for database_entry in database_entries.iloc:
        database_name     = database_entry['database']
        database_username = database_entry['username']
        database_password = database_entry['password']
        backup_destination_dir = os.path.join(volume_dir, "sql")
        pathlib.Path(backup_destination_dir).mkdir(parents=True, exist_ok=True)
        backup_destination_file = os.path.join(backup_destination_dir, f"{database_name}.backup.sql")
        if db_type == 'mariadb':
            backup_command = f"docker exec {container} /usr/bin/mariadb-dump -u {database_username} -p{database_password} {database_name} > {backup_destination_file}"
        elif db_type == 'postgres':
            if database_password:
                # Include PGPASSWORD in the command when a password is provided
                backup_command = (
                    f"PGPASSWORD={database_password} docker exec -i {container} "
                    f"pg_dump -U {database_username} -d {database_name} "
                    f"-h localhost > {backup_destination_file}"
                )
            else:
                # Exclude PGPASSWORD and use --no-password when the password is empty
                backup_command = (
                    f"docker exec -i {container} pg_dump -U {database_username} "
                    f"-d {database_name} -h localhost --no-password "
                    f"> {backup_destination_file}"
                )
        execute_shell_command(backup_command)
        print(f"Database backup for database {container} completed.")

def get_last_backup_dir(volume_name, current_backup_dir):
    """Get the most recent backup directory for the specified volume."""
    versions = sorted(os.listdir(VERSIONS_DIR), reverse=True)
    for version in versions:
        backup_dir = os.path.join(VERSIONS_DIR, version, volume_name, "files")
        # Ignore current backup dir
        if backup_dir != current_backup_dir:
            if os.path.isdir(backup_dir):
                return backup_dir
    print(f"No previous backups available for volume: {volume_name}")
    return None

def getStoragePath(volume_name):
    return execute_shell_command(f"docker volume inspect --format '{{{{ .Mountpoint }}}}' {volume_name}")

def backup_volume(volume_name, volume_dir):
    """Backup files of a volume with incremental backups."""
    print(f"Starting backup routine for volume: {volume_name}")
    files_rsync_destination_path = os.path.join(volume_dir, "files")
    pathlib.Path(files_rsync_destination_path).mkdir(parents=True, exist_ok=True)

    last_backup_dir = get_last_backup_dir(volume_name, files_rsync_destination_path)
    link_dest_option = f"--link-dest='{last_backup_dir}'" if last_backup_dir else ""

    source_dir = getStoragePath(volume_name)
    rsync_command = f"rsync -abP --delete --delete-excluded {link_dest_option} {source_dir} {files_rsync_destination_path}"
    execute_shell_command(rsync_command)
    print(f"Backup routine for volume: {volume_name} completed.")

def get_image_info(container):
    return execute_shell_command(f"docker inspect --format '{{{{.Config.Image}}}}' {container}")

def has_image(container,image):
    """Check if the container is using the image"""
    image_info = get_image_info(container)
    return image in image_info[0]
        
def stop_containers(containers):
    """Stop a list of containers."""
    container_list = ' '.join(containers)
    print(f"Stopping containers {container_list}...")
    execute_shell_command(f"docker stop {container_list}")
    
def start_containers(containers):
    """Start a list of containers."""
    container_list = ' '.join(containers)
    print(f"Start containers {container_list}...")
    execute_shell_command(f"docker start {container_list}")

def get_container_with_image(containers,image):
    for container in containers:
        if has_image(container,image):
            return container
    return False

def is_image_whitelisted(container, images):
    """Check if the container's image is one of the whitelisted images."""
    image_info = get_image_info(container)
    container_image = image_info[0]

    for image in images:
        if image in container_image:
            return True
    return False

def is_container_stop_required(containers):
    """Check if any of the containers are using images that are not whitelisted."""
    return any(not is_image_whitelisted(container, IMAGES_NO_STOP_REQUIRED) for container in containers)

def create_volume_directory(volume_name):
    """Create necessary directories for backup."""
    volume_dir = os.path.join(VERSION_DIR, volume_name)
    pathlib.Path(volume_dir).mkdir(parents=True, exist_ok=True)
    return volume_dir

def is_image_ignored(container):
    """Check if the container's image is one of the ignored images."""
    for image in IMAGES_NO_BACKUP_REQUIRED:
        if has_image(container, image):
            return True
    return False

def backup_with_containers_paused(volume_name, volume_dir, containers, shutdown):
    stop_containers(containers)
    backup_volume(volume_name, volume_dir)
    
    # Just restart containers if shutdown is false
    if not shutdown:
        start_containers(containers)

def backup_mariadb_or_postgres(container, volume_dir):
    '''Performs database image specific backup procedures'''
    for image in ['mariadb','postgres']:
        if has_image(container, image):
            backup_database(container, volume_dir, image)
            return True
    return False

def default_backup_routine_for_volume(volume_name, containers, shutdown):
    """Perform backup routine for a given volume."""
    volume_dir=""
    for container in containers:
        
        # Skip ignored images
        if is_image_ignored(container):
            print(f"Ignoring volume '{volume_name}' linked to container '{container}' with ignored image.")
            continue 

        # Directory which contains files and sqls
        volume_dir = create_volume_directory(volume_name)
        
        # Execute Database backup and exit if successfull
        if backup_mariadb_or_postgres(container, volume_dir):
            return

    # Execute backup if image is not ignored
    if volume_dir:    
        backup_volume(volume_name, volume_dir)
        if is_container_stop_required(containers):
            backup_with_containers_paused(volume_name, volume_dir, containers, shutdown)

def backup_everything(volume_name, containers, shutdown):
    """Perform file backup routine for a given volume."""
    volume_dir=create_volume_directory(volume_name)
    
    # Execute sql dumps
    for container in containers:
        backup_mariadb_or_postgres(container, volume_dir)

    # Execute file backups
    backup_volume(volume_name, volume_dir)
    backup_with_containers_paused(volume_name, volume_dir, containers, shutdown)

def main():
    parser = argparse.ArgumentParser(description='Backup Docker volumes.')
    parser.add_argument('--everything', action='store_true',
                        help='Force file backup for all volumes and additional execute database dumps')
    parser.add_argument('--shutdown', action='store_true',
                        help='Doesn\'t restart containers after backup')
    args = parser.parse_args()

    print('Start volume backups...')
    volume_names = execute_shell_command("docker volume ls --format '{{.Name}}'")
    
    for volume_name in volume_names:
        print(f'Start backup routine for volume: {volume_name}')
        containers = execute_shell_command(f"docker ps --filter volume=\"{volume_name}\" --format '{{{{.Names}}}}'")
        if not containers:
            print('Skipped due to no running containers using this volume.')
            continue
        if args.everything:
            backup_everything(volume_name, containers, args.shutdown)
        else:    
            default_backup_routine_for_volume(volume_name, containers, args.shutdown)

    print('Finished volume backups.')

if __name__ == "__main__":
    main()
