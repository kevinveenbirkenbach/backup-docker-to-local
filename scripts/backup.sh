#!/bin/bash
host_backup_folder_path="$HOME/Backup/docker/"
docker_backup_folder_path="/Backup/docker/"
mkdir -p "$host_backup_folder_path"
backup_folders=("/var/www/html/" "/var/lib/mysql/");
for docker_container_name in $(docker ps --format '{{.Names}}');
do
  #backup_dir_base_path="$docker_backup_folder_path""archive/$(date '+%Y%m%d%H%M%S')/""$docker_container_name/"
  echo "stop container: $docker_container_name" && docker stop "$docker_container_name"
  for rsync_source_path in "${backup_folders[@]}";
  do
    rsync_docker_destination_path="$docker_backup_folder_path""last/""$docker_container_name$rsync_source_path";
    #backup_dir_path="$backup_dir_base_path$rsync_source_path";
    echo "trying to backup $rsync_source_path..."
    rsync_host_destination_path="$HOME$rsync_docker_destination_path";
    mkdir -p "$rsync_host_destination_path";
    (docker run --rm --volumes-from "$docker_container_name" -v "$host_backup_folder_path:$docker_backup_folder_path" "kevinveenbirkenbach/alpine-rsync" rsync -a --delete "$rsync_source_path" "$rsync_docker_destination_path") &> /dev/null 
    || rmdir "$rsync_host_destination_path" && echo "skipped.";
  done
  echo "start container: $docker_container_name" && docker start "$docker_container_name"
done
