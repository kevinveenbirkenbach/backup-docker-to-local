#!/bin/python
# Backups volumes of running containers

import subprocess
import os
import re
import pathlib
import pandas
from datetime import datetime

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

def get_machine_id():
    """Get the machine identifier."""
    return execute_shell_command("sha256sum /etc/machine-id")[0][0:64]

def create_backup_directories(base_dir, machine_id, repository_name, backup_time):
    """Create necessary directories for backup."""
    version_dir = os.path.join(base_dir, machine_id, repository_name, backup_time)
    pathlib.Path(version_dir).mkdir(parents=True, exist_ok=True)
    return version_dir

def get_database_name(container):
    """Extract the database name from the container name."""
    return re.split("(_|-)(database|db)", container)[0]

def backup_database(container, databases, version_dir):
    """Backup database if applicable."""
    database_name = get_database_name(container)
    database_entry = databases.loc[databases['database'] == database_name].iloc[0]
    mysqldump_destination_dir = os.path.join(version_dir, "sql")
    pathlib.Path(mysqldump_destination_dir).mkdir(parents=True, exist_ok=True)
    mysqldump_destination_file = os.path.join(mysqldump_destination_dir, "backup.sql")
    database_backup_command = f"docker exec {container} /usr/bin/mariadb-dump -u {database_entry['username']} -p{database_entry['password']} {database_entry['database']} > {mysqldump_destination_file}"
    execute_shell_command(database_backup_command)

def backup_volume(volume_name, version_dir):
    """Backup files of a volume."""
    files_rsync_destination_path = os.path.join(version_dir, volume_name, "files")
    pathlib.Path(files_rsync_destination_path).mkdir(parents=True, exist_ok=True)
    source_dir = f"/var/lib/docker/volumes/{volume_name}/_data/"
    rsync_command = f"rsync -abP --delete --delete-excluded {source_dir} {files_rsync_destination_path}"
    execute_shell_command(rsync_command)

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

        for container in containers:
            if container != 'akaunting':
                backup_database(container, databases, version_dir)
            backup_volume(volume_name, version_dir)

    print('Finished volume backups.')
    print('Restart docker service...')
    execute_shell_command("systemctl restart docker")
    print('Finished backup routine.')

if __name__ == "__main__":
    main()
