#!/bin/bash
host_backup_folder_path="$HOME/Backup/docker/"
docker_backup_folder_path="/Backup/docker/"
mkdir -p "$host_backup_folder_path"
backup_folders=("/var/www/html/" "/var/lib/mysql/");
for docker_container_id in $(docker ps -q);
do
  #backup_dir_base_path="$docker_backup_folder_path""archive/$(date '+%Y%m%d%H%M%S')/""$docker_container_id/"
  echo "stop container: $docker_container_id" && docker stop "$docker_container_id"
  for rsync_source_path in "${backup_folders[@]}";
  do
    rsync_destination_path="$docker_backup_folder_path""last/""$docker_container_id$rsync_source_path";
    #backup_dir_path="$backup_dir_base_path$rsync_source_path";
    echo "trying to backup $rsync_source_path..."
    mkdir -p "$HOME$rsync_destination_path"
    docker run --rm --volumes-from "$docker_container_id" -v "$host_backup_folder_path:$docker_backup_folder_path" "kevinveenbirkenbach/alpine-rsync" rsync -a --delete $rsync_source_path $rsync_destination_path
  done
  echo "start container: $docker_container_id" && docker start "$docker_container_id"
done
