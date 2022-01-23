#!/bin/python
# Backups volumes of running containers
#
import subprocess, os, sys, pathlib
from datetime import datetime
from pprint import pprint

def bash(command):
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
repository_name=os.path.basename(os.path.dirname(__file__))
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
        print("stop containers:");
        print_bash("docker stop " + list_to_string(containers))
        source_path_command="docker inspect --format \"{{ range .Mounts }}{{ if eq .Type \\\"volume\\\"}}{{ if eq .Name \\\"" + volume_name +"\\\"}}{{ println .Destination }}{{ end }}{{ end }}{{ end }}\" \""+ container +"\""
        source_path_command_result_filtered=list(filter(None, bash(source_path_command)))
        for source_path in source_path_command_result_filtered:
            destination_path=backup_repository_folder+"latest/"+ volume_name
            sql_destination_path=destination_path + "/files"
            sql_destination_path=destination_path + "/sql"
            log_path=backup_repository_folder + "log.txt"
            backup_dir_path=backup_repository_folder + "diffs/"+ backup_time + "/" + volume_name
            files_backup_dir_path=backup_dir_path + "/files"
            sql_backup_dir_path=backup_dir_path + "/sql"
            if os.path.exists(destination_path):
                print("backup volume: " + volume_name);
            else:
                print("first backup volume: " + volume_name);
                pathlib.Path(sql_destination_path).mkdir(parents=True, exist_ok=True)
                pathlib.Path(files_backup_dir_path).mkdir(parents=True, exist_ok=True)
                pathlib.Path(sql_destination_path).mkdir(parents=True, exist_ok=True)
                pathlib.Path(sql_backup_dir_path).mkdir(parents=True, exist_ok=True)
            print_bash("docker run --rm --volumes-from " + container + " -v "+backups_folder+":"+ backups_folder +" \"kevinveenbirkenbach/alpine-rsync\" sh -c \"rsync -abP --delete --delete-excluded --log-file=" + log_path +" --backup-dir=" + files_backup_dir_path +" '"+ source_path +"/' " + sql_destination_path +"\"")
        print("start containers:")
        print_bash("docker start " + list_to_string(containers))
    print("end backup routine for volume:" + volume_name)
print('finished volume backups.')
print('restart docker service...')
print_bash("systemctl restart docker")
print('finished backup routine.')
