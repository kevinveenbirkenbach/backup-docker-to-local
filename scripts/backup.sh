#!/bin/bash
host_backup_folder_path="$HOME/Backup/docker/"
docker_backup_folder_path="/Backup/docker/"
mkdir -p "$host_backup_folder_path"
docker_container_ids="$(docker ps -q)";
backup_folders=("/var/www/html/" "/var/lib/mysql/");
for docker_container_id in "${docker_container_ids[@]}";
do
  #backup_dir_base_path="$docker_backup_folder_path""archive/$(date '+%Y%m%d%H%M%S')/""$docker_container_id/"
  docker stop "$docker_container_id"
  for rsync_source_path in "${backup_folders[@]}";
  do
    rsync_destination_path="$docker_backup_folder_path""last/""$docker_container_id/$rsync_source_path";
    #backup_dir_path="$backup_dir_base_path$rsync_source_path";
    docker run --rm --volumes-from "$docker_container_id" -v "$host_backup_folder_path:$docker_backup_folder_path" ubuntu bash -c “test -e $rsync_source_path && rsync -a --delete $rsync_source_path $rsync_destination_path”
  done
  docker start "$docker_container_id"
done
