#!/bin/bash
# @param $1 [optional] : The path in which the backups folder will be created.
backup_time="$(date '+%Y%m%d%H%M%S')"
docker_backups_mount="/Backups/"
native_backups_mount_prefix="$(test -z "$1" && echo "$HOME" || echo "$1")"
native_backups_mount="$native_backups_mount_prefix$docker_backups_mount"
for docker_container_name in $(docker ps --format '{{.Names}}');
do
  echo "stop container: $docker_container_name" && docker stop "$docker_container_name"
  for source_path in $(docker inspect --format '{{ range .Mounts }}{{ if eq .Type "volume" }}{{ println .Destination }}{{ end }}{{ end }}' "$docker_container_name");
  do
    application_path="$docker_backups_mount$(cat /etc/machine-id)/docker/$docker_container_name/";
    destination_path="$application_path""latest""$source_path";
    log_path="$application_path""log.txt";
    backup_dir_path="$application_path""diffs/$backup_time$source_path";
    if [ -d "$native_backups_mount_prefix$destination_path" ]
      then
        echo "backup: $source_path"
      else
        echo "first backup: $source_path"
        mkdir -vp "$native_backups_mount_prefix$destination_path";
        mkdir -vp "$native_backups_mount_prefix$backup_dir_path";
    fi
    docker run --rm --volumes-from "$docker_container_name" -v "$native_backups_mount:$docker_backups_mount" "kevinveenbirkenbach/alpine-rsync" sh -c "
    rsync -abvv --delete --delete-excluded --log-file=$log_path --backup-dir=$backup_dir_path '$source_path/' $destination_path";
  done
  echo "start container: $docker_container_name" && docker start "$docker_container_name"
done
