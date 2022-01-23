#!/bin/python
# Backups volumes of running containers
#
import subprocess
import os, sys
from datetime import datetime

def bash(command):
    stdout=subprocess.Popen([command],stdout=subprocess.PIPE, shell=True).stdout.read()
    if isinstance(stdout, list):
        return subprocess.Popen([command],stdout=subprocess.PIPE, shell=True).stdout.read()
    else:
        return subprocess.Popen([command],stdout=subprocess.PIPE, shell=True).stdout.read()

def list_to_string(list):
    list_string=""
    for element in list:
        list_string=list_string + " " + (element.decode("utf-8"))
    return list_string;

print('start backup routine...')
print('start volume backups...')
backup_time=datetime.now().strftime("%Y%m%d%H%M%S")
backups_folder='/Backups/'
repository_name=os.path.basename(os.path.dirname(__file__))
machine_id=bash("sha256sum /etc/machine-id").decode("utf-8")[0:64]
backup_repository_folder=backups_folder + machine_id + "/" + repository_name + "/"
volume_names=bash("docker volume ls --format '{{.Name}}'").splitlines()
for volume_name in volume_names:
    volume_name=volume_name.decode("utf-8")
    print('start backup routine for volume: ' + volume_name);
    containers=bash("docker ps --filter volume=\""+ volume_name +"\" --format '{{.Names}}'").splitlines()
    container=containers[0].decode("utf-8")
    if len(containers) == 0:
        print('skipped due to no running containers using this volume.');
    else:
        print("stop containers:");
        print(bash("docker stop " + list_to_string(containers)))
#       for source_path in $(docker inspect --format "{{ range .Mounts }}{{ if eq .Type \"volume\"}}{{ if eq .Name \"$volume_name\"}}{{ println .Destination }}{{ end }}{{ end }}{{ end }}" "$container");
#       do
#         destination_path="$backup_repository_folder""latest/$volume_name" &&
#         raw_destination_path="$destination_path/raw" &&
#         prepared_destination_path="$destination_path/prepared" &&
#         log_path="$backup_repository_folder""log.txt" &&
#         backup_dir_path="$backup_repository_folder""diffs/$backup_time/$volume_name" &&
#         raw_backup_dir_path="$backup_dir_path/raw" &&
#         prepared_backup_dir_path="$backup_dir_path/prepared" || exit 1
#         if [ -d "$destination_path" ]
#           then
#             print('backup volume: $volume_name');
#           else
#             print('first backup volume: $volume_name');
#             mkdir -vp "$raw_destination_path" &&
#             mkdir -vp "$raw_backup_dir_path" &&
#             mkdir -vp "$prepared_destination_path" &&
#             mkdir -vp "$prepared_backup_dir_path" || exit 1
#         fi
#         docker run --rm --volumes-from "$container" -v "$backups_folder:$backups_folder" "kevinveenbirkenbach/alpine-rsync" sh -c "
#         rsync -abP --delete --delete-excluded --log-file=$log_path --backup-dir=$raw_backup_dir_path '$source_path/' $raw_destination_path" &&
        print(bash("docker start " + list_to_string(containers)))
#       done
#   fi
#   print('end backup routine for volume: $volume_name');
# done
print('finished volume backups.')
print('restart docker service...')
# systemctl restart docker || exit 1
print('finished backup routine.')
