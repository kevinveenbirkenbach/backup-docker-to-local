#!/bin/python
# Backups volumes of running containers
#
import subprocess, os, sys
from datetime import datetime

def bash(command):
    out, err=subprocess.Popen([command],stdout=subprocess.PIPE, shell=True).communicate()
    stdout=out.read().splitlines()
    output=[]
    for line in stdout:
        output.append(line.decode("utf-8"))
    if err > 0:
        raise Exception("Error is greater then 0", output, command)
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
    container=containers[0]
    if len(containers) == 0:
        print('skipped due to no running containers using this volume.');
    else:
        print("stop containers:");
        print_bash("docker stop " + list_to_string(containers))
        for source_path in bash("docker inspect --format \"{{ range .Mounts }}{{ if eq .Type \\\"volume\\\"}}{{ if eq .Name \\\"" + volume_name +"\\\"}}{{ println .Destination }}{{ end }}{{ end }}{{ end }}\" \""+ container +"\""):
            destination_path=backup_repository_folder+"latest/"+ volume_name
            raw_destination_path="destination_path/raw"
            prepared_destination_path=destination_path + "/prepared"
            log_path=backup_repository_folder + "log.txt"
            backup_dir_path=backup_repository_folder + "diffs/"+ backup_time + "/" + volume_name
            raw_backup_dir_path=backup_dir_path + "/raw"
            prepared_backup_dir_path=backup_dir_path + "/prepared"
            if path.exists(destination_path):
                print("backup volume: " + volume_name);
            else:
                print("first backup volume" + volume_name);
                os.mkdir(raw_destination_path)
                os.mkdir(raw_backup_dir_path)
                os.mkdir(prepared_destination_path)
                os.mkdir(prepared_backup_dir_path)
        print_bash("rsync -abP --delete --delete-excluded --log-file=" + log_path +" --backup-dir=" + raw_backup_dir_path +" '"+ source_path +"/' " + raw_destination_path)
        print_bash("docker run --rm --volumes-from " + container + " -v "+backups_folder+":"+ backups_folder +" \"kevinveenbirkenbach/alpine-rsync\" sh -c ")
        print("start containers:")
        print_bash("docker start " + list_to_string(containers))
    print("end backup routine for volume:" + volume_name)
print('finished volume backups.')
print('restart docker service...')
print_bash("systemctl restart docker")
print('finished backup routine.')
