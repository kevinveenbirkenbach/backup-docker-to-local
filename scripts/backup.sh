#!/bin/bash

backup_time="$(date '+%Y%m%d%H%M%S')"
docker_backups_mount="/Backups/"
native_backups_mount_prefix="$HOME"
native_backups_mount="$native_backups_mount_prefix$docker_backups_mount"
for docker_container_name in $(docker ps --format '{{.Names}}');
do
  echo "stop container: $docker_container_name" && docker stop "$docker_container_name"
  for source_path in $(docker inspect --format '{{ range .Mounts }}{{ if eq .Type "volume" }}{{ println .Destination }}{{ end }}{{ end }}' "$docker_container_name");
  do
    application_path="$docker_backups_mount$(cat /etc/machine-id)/docker/$docker_container_name"
    first_destination_path="$application_path""first""$source_path";
    latest_destination_path="$application_path""latest""$source_path";
    backup_dir_path="$application_path""diffs/$backup_time/$source_path"
    if [ -d "$first_destination_path)" ]
      then
        echo "backup: $source_path"
        destination_path="$latest_destination_path";
      else
        echo "first backup: $source_path"
        destination_path="$first_destination_path";
    fi
    mkdir -p "$native_backups_mount_prefix$destination_path";
    docker run --rm --volumes-from "$docker_container_name" -v "$native_backups_mount:$docker_backups_mount" "kevinveenbirkenbach/alpine-rsync" sh -c "
    test -d $source_path &&
    mkdir -p \"$destination_path\" &&
    rsync -a --delete --backup-dir=\"$backup_dir_path\" $source_path $destination_path ||
    mkdir -p \"$(dirname "$destination_path")\" &&
    rsync -a --delete --backup-dir=\"$(dirname "$backup_dir_path")\" $source_path $(dirname "$destination_path")";
  done
  echo "start container: $docker_container_name" && docker start "$docker_container_name"
done
