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

DOCKER_COMPOSE_HARD_RESTART_REQUIRED = ['mailu']

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
    # The function is defined to take one parameter, 'container', 
    # which is expected to be a string.

    # This line uses regular expressions to split the 'container' string.
    # 're.split' is a method that divides a string into a list, based on the occurrences of a pattern.
    if container in ['central-mariadb', 'central-postgres']:
        instance_name = container
    else:
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

def stamp_directory():
    """Stamp a directory using directory-validator."""
    stamp_command = f"python {SCRIPTS_DIRECTORY}/directory-validator/directory-validator.py --stamp {VERSION_DIR}"
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

    # Filter the DataFrame for the given instance_name
    database_entries = DATABASES.loc[DATABASES['instance'] == instance_name]

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
            execute_shell_command(backup_command)
        if db_type == 'postgres':
            cluster_file = os.path.join(backup_destination_dir, f"{instance_name}.cluster.backup.sql")

            if not database_name:
                fallback_pg_dumpall(container, database_username, database_password, cluster_file)
                return

            try:
                if database_password:
                    backup_command = (
                        f"PGPASSWORD={database_password} docker exec -i {container} "
                        f"pg_dump -U {database_username} -d {database_name} "
                        f"-h localhost > {backup_destination_file}"
                    )
                else:
                    backup_command = (
                        f"docker exec -i {container} pg_dump -U {database_username} "
                        f"-d {database_name} -h localhost --no-password "
                        f"> {backup_destination_file}"
                    )
                execute_shell_command(backup_command)
            except BackupException as e:
                print(f"pg_dump failed: {e}")
                print(f"Falling back to pg_dumpall for instance '{instance_name}'")
                fallback_pg_dumpall(container, database_username, database_password, cluster_file)
        print(f"Database backup for database {container} completed.")

def get_last_backup_dir(volume_name, current_backup_dir):
    """Get the most recent backup directory for the specified volume."""
    versions = sorted(os.listdir(VERSIONS_DIR), reverse=True)
    for version in versions:
        backup_dir = os.path.join(VERSIONS_DIR, version, volume_name, "files", "")
        # Ignore current backup dir
        if backup_dir != current_backup_dir:
            if os.path.isdir(backup_dir):
                return backup_dir
    print(f"No previous backups available for volume: {volume_name}")
    return None

def getStoragePath(volume_name):
    path = execute_shell_command(f"docker volume inspect --format '{{{{ .Mountpoint }}}}' {volume_name}")[0] 
    return f"{path}/"

def getFileRsyncDestinationPath(volume_dir):
    path = os.path.join(volume_dir, "files")
    return f"{path}/"

def fallback_pg_dumpall(container, username, password, backup_destination_file):
    """Fallback function to run pg_dumpall if pg_dump fails or no DB is defined."""
    print(f"Running pg_dumpall for container '{container}'...")
    command = (
        f"PGPASSWORD={password} docker exec -i {container} "
        f"pg_dumpall -U {username} -h localhost > {backup_destination_file}"
    )
    execute_shell_command(command)

def backup_volume(volume_name, volume_dir):
    try:
        """Backup files of a volume with incremental backups."""
        print(f"Starting backup routine for volume: {volume_name}")
        files_rsync_destination_path = getFileRsyncDestinationPath(volume_dir)
        pathlib.Path(files_rsync_destination_path).mkdir(parents=True, exist_ok=True)

        last_backup_dir = get_last_backup_dir(volume_name, files_rsync_destination_path)
        link_dest_option = f"--link-dest='{last_backup_dir}'" if last_backup_dir else ""

        source_dir = getStoragePath(volume_name)
        rsync_command = f"rsync -abP --delete --delete-excluded {link_dest_option} {source_dir} {files_rsync_destination_path}"
        execute_shell_command(rsync_command)
    except BackupException as e:
        if "file has vanished" in e.args[0]:
            print("Warning: Some files vanished before transfer. Continuing.")
        else:
            raise
    print(f"Backup routine for volume: {volume_name} completed.")

def get_image_info(container):
    return execute_shell_command(f"docker inspect --format '{{{{.Config.Image}}}}' {container}")

def has_image(container,image):
    """Check if the container is using the image"""
    image_info = get_image_info(container)
    return image in image_info[0]

def change_containers_status(containers,status):
    """Stop a list of containers."""
    if containers:
        container_list = ' '.join(containers)
        print(f"{status} containers {container_list}...")
        execute_shell_command(f"docker {status} {container_list}")
    else:
        print(f"No containers to {status}.")    

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
    change_containers_status(containers,'stop')
    backup_volume(volume_name, volume_dir)
    
    # Just restart containers if shutdown is false
    if not shutdown:
        change_containers_status(containers,'start')

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
    for dir_entry in os.scandir(parent_directory):
        if dir_entry.is_dir():
            dir_path = dir_entry.path
            dir_name = os.path.basename(dir_path)
            print(f"Checking directory: {dir_path}")
            
            docker_compose_file = os.path.join(dir_path, "docker-compose.yml")
            
            if os.path.isfile(docker_compose_file):
                print(f"Found docker-compose.yml in {dir_path}.")
                if dir_name in DOCKER_COMPOSE_HARD_RESTART_REQUIRED:
                    print(f"Directory {dir_name} detected. Performing hard restart...")
                    hard_restart_docker_services(dir_path)
                else:
                    print(f"No restart required for services in {dir_path}...")
            else:
                print(f"No docker-compose.yml found in {dir_path}. Skipping.")

def main():
    parser = argparse.ArgumentParser(description='Backup Docker volumes.')
    parser.add_argument('--everything', action='store_true',
                        help='Force file backup for all volumes and additional execute database dumps')
    parser.add_argument('--shutdown', action='store_true',
                        help='Doesn\'t restart containers after backup')
    parser.add_argument('--compose-dir', type=str, required=True, help='Path to the parent directory containing docker-compose setups')
    args = parser.parse_args()

    print('Start volume backups...')
    volume_names = execute_shell_command("docker volume ls --format '{{.Name}}'")
    
    for volume_name in volume_names:
        print(f'Start backup routine for volume: {volume_name}')
        containers = execute_shell_command(f"docker ps --filter volume=\"{volume_name}\" --format '{{{{.Names}}}}'")
        if args.everything:
            backup_everything(volume_name, containers, args.shutdown)
        else:    
            default_backup_routine_for_volume(volume_name, containers, args.shutdown)
    stamp_directory()
    print('Finished volume backups.')
    
    # Handle Docker Compose services
    print('Handling Docker Compose services...')
    handle_docker_compose_services(args.compose_dir)

if __name__ == "__main__":
    main()
