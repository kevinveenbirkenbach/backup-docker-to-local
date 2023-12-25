#!/bin/python
# Backups volumes of running containers

import subprocess
import os
import re
import pathlib
import pandas
from datetime import datetime

#Ok 
class BackupException(Exception):
    """Generic exception for backup errors."""
    pass

# OK
def execute_shell_command(command):
    """Execute a shell command and return its output."""
    print(command)
    process = subprocess.Popen([command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    out, err = process.communicate()
    if process.returncode != 0:
        raise BackupException(f"Error in command: {command}\nOutput: {out}\nError: {err}\nExit code: {process.returncode}")
    return [line.decode("utf-8") for line in out.splitlines()]

# OK
def get_machine_id():
    """Get the machine identifier."""
    return execute_shell_command("sha256sum /etc/machine-id")[0][0:64]

# OK
def create_backup_directories(base_dir, machine_id, repository_name, backup_time):
    """Create necessary directories for backup."""
    version_dir = os.path.join(base_dir, machine_id, repository_name, backup_time)
    pathlib.Path(version_dir).mkdir(parents=True, exist_ok=True)
    return version_dir

# OK
def get_database_name(container):
    """Extract the database name from the container name."""
    return re.split("(_|-)(database|db)", container)[0]

# OK 
def backup_mariadb(container, databases, version_dir):
    """Backup database if applicable."""
    database_name = get_database_name(container)
    database_entry = databases.loc[databases['database'] == database_name].iloc[0]
    mysqldump_destination_dir = os.path.join(version_dir, "sql")
    pathlib.Path(mysqldump_destination_dir).mkdir(parents=True, exist_ok=True)
    mysqldump_destination_file = os.path.join(mysqldump_destination_dir, f"{database_name}_backup.sql")
    database_backup_command = f"docker exec {container} /usr/bin/mariadb-dump -u {database_entry['username']} -p{database_entry['password']} {database_entry['database']} > {mysqldump_destination_file}"
    execute_shell_command(database_backup_command)

def backup_postgres(container, databases, version_dir):
    """Backup PostgreSQL database if applicable."""
    database_name = get_database_name(container)
    database_entry = databases.loc[databases['database'] == database_name].iloc[0]
    pg_dump_destination_dir = os.path.join(version_dir, "sql")
    pathlib.Path(pg_dump_destination_dir).mkdir(parents=True, exist_ok=True)
    pg_dump_destination_file = os.path.join(pg_dump_destination_dir, f"{database_name}_backup.sql")
    # Docker command to execute pg_dump and save the output on the host system
    database_backup_command = (
        f"docker exec -i {container} pg_dump -U {database_entry['username']} "
        f"-d {database_entry['database']} -h localhost "
        f"--no-password"
    )
    # Redirect the output of docker exec to a file on the host system
    full_command = f"PGPASSWORD={database_entry['password']} {database_backup_command} > {pg_dump_destination_file}"
    execute_shell_command(full_command)


# OK 
def backup_volume(volume_name, version_dir):
    """Backup files of a volume."""
    files_rsync_destination_path = os.path.join(version_dir, volume_name, "files")
    pathlib.Path(files_rsync_destination_path).mkdir(parents=True, exist_ok=True)
    source_dir = f"/var/lib/docker/volumes/{volume_name}/_data/"
    rsync_command = f"rsync -abP --delete --delete-excluded {source_dir} {files_rsync_destination_path}"
    execute_shell_command(rsync_command)

# OK
def is_image(container,image):
    """Check if the container is using a MariaDB image."""
    image_info = execute_shell_command(f"docker inspect {container} | jq -r '.[].Config.Image'")
    return image in image_info[0]

# OK
def stop_containers(containers):
    """Stop a list of containers."""
    for container in containers:
        print(f"Stopping container {container}...")
        execute_shell_command(f"docker stop {container}")
# OK
def start_containers(containers):
    """Start a list of stopped containers."""
    for container in containers:
        print(f"Starting container {container}...")
        execute_shell_command(f"docker start {container}")

# OK
def any_has_image(containers,image):
    for container in containers:
        if is_mariadb_container(container,image):
            return container
    return False

def is_whitelisted(container, images):
    """Check if the container's image is one of the whitelisted images."""
    image_info = execute_shell_command(f"docker inspect {container} | jq -r '.[].Config.Image'")
    container_image = image_info[0]

    for image in images:
        if image in container_image:
            return True
    return False

def is_any_not_whitelisted(containers, images):
    """Check if any of the containers are using images that are not whitelisted."""
    return any(not is_whitelisted(container, images) for container in containers)

def main():
    print('Start backup routine...')
    dirname = os.path.dirname(__file__)
    repository_name = os.path.basename(dirname)
    machine_id = get_machine_id()
    backups_dir = '/Backups/'
    backup_time = datetime.now().strftime("%Y%m%d%H%M%S")
    version_dir = create_backup_directories(backups_dir, machine_id, repository_name, backup_time)

    print('Start volume backups...')
    databases = pandas.read_csv(os.path.join(dirname, "databases.csv"), sep=";")
    volume_names = execute_shell_command("docker volume ls --format '{{.Name}}'")
    
    for volume_name in volume_names:
        print(f'Start backup routine for volume: {volume_name}')
        containers = execute_shell_command(f"docker ps --filter volume=\"{volume_name}\" --format '{{.Names}}'")
        if not containers:
            print('Skipped due to no running containers using this volume.')
            continue

        mariadb_container = get_container_with_image(containers,'mariadb')
        if mariadb_container:
            print(f"Backup MariaDB database for container: {mariadb_container}")
            backup_mariaddb(mariadb_container, databases, version_dir)
        else:
            postgres_container = get_container_with_image(containers,'postgres')
            if postgres_container:
                print(f"Backup Postgres database for container: {postgres_container}")
                backup_postgres(postgres_container, databases, version_dir)
            # Data backup
            else:
                # Just copy without stopping
                backup_volume(volume_name, version_dir)
                # If container if not whitelisted stop and start container afterwards.
                if is_any_not_whitelisted(containers, []):
                    stop_containers(containers)
                    backup_volume(volume_name, version_dir)
                    start_containers(containers)

    print('Finished volume backups.')
    #print('Restart docker service...')
    #execute_shell_command("systemctl restart docker")
    #print('Finished backup routine.')

if __name__ == "__main__":
    main()
