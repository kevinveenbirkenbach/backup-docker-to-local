#!/bin/python
# Backups volumes of running containers
#
import subprocess, os, pathlib, pandas
from datetime import datetime


def bash(command):
    print(command)
    process = subprocess.Popen([command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    out, err = process.communicate()
    stdout = out.splitlines()
    output = []
    for line in stdout:
        output.append(line.decode("utf-8"))
    if process.wait() > bool(0):
        print(command, out, err)
        raise Exception("Error is greater then 0")
    return output


def print_bash(command):
    output = bash(command)
    print(list_to_string(output))
    return output


def list_to_string(list):
    return str(' '.join(list))


print('start backup routine...')
print('start volume backups...')
backup_time = datetime.now().strftime("%Y%m%d%H%M%S")
backups_folder = '/Backups/'
dirname = os.path.dirname(__file__)
repository_name = os.path.basename(dirname)
print('load connection data...')
databases = pandas.read_csv(dirname + "/databases.csv", sep=";")
machine_id = bash("sha256sum /etc/machine-id")[0][0:64]
backup_repository_folder = backups_folder + machine_id + "/" + repository_name + "/"
volume_names = bash("docker volume ls --format '{{.Name}}'")
for volume_name in volume_names:
    print('start backup routine for volume: ' + volume_name)
    containers = bash("docker ps --filter volume=\"" + volume_name + "\" --format '{{.Names}}'")
    if len(containers) == 0:
        print('skipped due to no running containers using this volume.')
    else:
        container = containers[0]
        versions_dir_path = backup_repository_folder + "versions/"
        general_destination_dir = versions_dir_path + backup_time + "/" + volume_name
        databases_entries = databases.loc[databases['container'] == container]
        if len(databases_entries) == 1:
            print("Backup database...")
            mysqldump_destination_dir = general_destination_dir + "/sql"
            mysqldump_destination_file = mysqldump_destination_dir + "/backup.sql"
            pathlib.Path(mysqldump_destination_dir).mkdir(parents=True, exist_ok=True)
            database_entry = databases_entries.iloc[0]
            database_backup_command = "docker exec " + database_entry["container"] + " /usr/bin/mysqldump -u " + database_entry["username"] + " -p" + database_entry["password"] + " " + database_entry["database"] + " > " + mysqldump_destination_file
            print_bash(database_backup_command)
        else:
            print("Backup files...")
            files_rsync_destination_path = general_destination_dir + "/files"
            pathlib.Path(files_rsync_destination_path).mkdir(parents=True, exist_ok=True)
            versions = os.listdir(versions_dir_path)
            versions.sort(reverse=True)
            if len(versions) > 1:
                last_version = versions[1]
                last_version_files_dir = versions_dir_path + last_version + "/" + volume_name + "/files"
                if os.path.isdir(last_version_files_dir):
                    link_dest_parameter="--link-dest='" + last_version_files_dir + "' "
                else:
                    print("No previous version exists in path "+ last_version_files_dir + ".")
                    link_dest_parameter=""
            else:
                print("No previous version exists in path "+ last_version_files_dir + ".")
                link_dest_parameter=""
            source_dir = "/var/lib/docker/volumes/" + volume_name + "/_data/"
            rsync_command = "rsync -abP --delete --delete-excluded " + link_dest_parameter + source_dir + " " + files_rsync_destination_path
            print_bash(rsync_command)
            print("stop containers...")
            print("Backup data after container is stopped...")
            print_bash("docker stop " + list_to_string(containers))
            print_bash(rsync_command)
            print("start containers...")
            print_bash("docker start " + list_to_string(containers))
    print("end backup routine for volume:" + volume_name)
print('finished volume backups.')
print('restart docker service...')
print_bash("systemctl restart docker")
print('finished backup routine.')
