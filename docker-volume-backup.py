#!/bin/python
# Backups volumes of running containers
#
import subprocess, os, sys, pathlib, csv, pandas
from datetime import datetime

def bash(command):
    print(command);
    process=subprocess.Popen([command],stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    out, err=process.communicate()
    stdout=out.splitlines()
    output=[]
    for line in stdout:
        output.append(line.decode("utf-8"))
    if process.wait() > bool(0):
        print(command,out,err);
        raise Exception("Error is greater then 0")
    return output

def print_bash(command):
    output=bash(command)
    print(list_to_string(output))
    return output

def list_to_string(list):
    return str(' '.join(list));

print('start backup routine...')
print('start volume backups...')
backup_time=datetime.now().strftime("%Y%m%d%H%M%S")
backups_folder='/Backups/'
dirname=os.path.dirname(__file__)
repository_name=os.path.basename(dirname)
print('load connection data...');
databases=pandas.read_csv(dirname + "/databases.csv",sep=";");
machine_id=bash("sha256sum /etc/machine-id")[0][0:64]
backup_repository_folder=backups_folder + machine_id + "/" + repository_name + "/"
volume_names=bash("docker volume ls --format '{{.Name}}'")
for volume_name in volume_names:
    print('start backup routine for volume: ' + volume_name);
    containers=bash("docker ps --filter volume=\""+ volume_name +"\" --format '{{.Names}}'")
    if len(containers) == 0:
        print('skipped due to no running containers using this volume.');
    else:
        container=containers[0]
        source_path="/var/lib/docker/volumes/" + volume_name + "/_data"
        destination_path=backup_repository_folder+"latest/"+ volume_name
        log_path=backup_repository_folder + "log.txt"
        backup_dir_path=backup_repository_folder + "diffs/"+ backup_time + "/" + volume_name
        databases_entries=databases.loc[databases['container'] == container];
        if len(databases_entries) == 1:
            print("Backup database...")
            sql_destination_path=destination_path + "/sql"
            sql_backup_dir_path=backup_dir_path + "/sql"
            sql_destination_dir_file_path=sql_destination_path+"/backup.sql"
            pathlib.Path(sql_destination_path).mkdir(parents=True, exist_ok=True)
            pathlib.Path(sql_backup_dir_path).mkdir(parents=True, exist_ok=True)
            database_entry=databases_entries.iloc[0];
            database_backup_command="docker exec "+ database_entry["container"] + " /usr/bin/mysqldump -u "+ database_entry["username"] + " -p"+ database_entry["password"] + " "+ database_entry["database"] + " > " + sql_destination_dir_file_path
            print_bash(database_backup_command)
            print_bash("cp -v " + sql_destination_dir_file_path + " " + sql_backup_dir_path)
        else:
            print("Backup files...")
            files_destination_path=destination_path + "/files"
            files_backup_dir_path=backup_dir_path + "/files"
            pathlib.Path(files_backup_dir_path).mkdir(parents=True, exist_ok=True)
            pathlib.Path(files_destination_path).mkdir(parents=True, exist_ok=True)
            print("stop containers...");
            print_bash("docker stop " + list_to_string(containers))
            print_bash("rsync -abP --delete --delete-excluded --log-file=" + log_path +" --backup-dir=" + files_backup_dir_path +" '"+ source_path +"/' " + files_destination_path)
            print("start containers...")
            print_bash("docker start " + list_to_string(containers))
    print("end backup routine for volume:" + volume_name)
print('finished volume backups.')
print('restart docker service...')
print_bash("systemctl restart docker")
print('finished backup routine.')
