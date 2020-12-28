#!/bin/bash
backup_time="$(date '+%Y%m%d%H%M%S')";
backups_folder="/Backups/";
for docker_container_name in $(docker ps --format '{{.Names}}');
do
  echo "stop container: $docker_container_name" && docker stop "$docker_container_name"
  for source_path in $(docker inspect --format '{{ range .Mounts }}{{ if eq .Type "volume" }}{{ println .Destination }}{{ end }}{{ end }}' "$docker_container_name");
  do
    repository_name="$(cd "$(dirname "$(readlink -f "${0}")")" && basename `git rev-parse --show-toplevel`)";
    machine_id="$(sha256sum /etc/machine-id | head -c 64)";
    backup_repository_folder="$backups_folder$machine_id/$repository_name/";
    destination_path="$backup_repository_folder""latest/$docker_container_name$source_path";
    log_path="$backup_repository_folder""log.txt";
    backup_dir_path="$backup_repository_folder""diffs/$backup_time/$docker_container_name$source_path";
    if [ -d "$destination_path" ]
      then
        echo "backup: $source_path";
      else
        echo "first backup: $source_path"
        mkdir -vp "$destination_path";
        mkdir -vp "$backup_dir_path";
    fi
    docker run --rm --volumes-from "$docker_container_name" -v "$backups_folder:$backups_folder" "kevinveenbirkenbach/alpine-rsync" sh -c "
    rsync -abvv --delete --delete-excluded --log-file=$log_path --backup-dir=$backup_dir_path '$source_path/' $destination_path";
  done
  echo "start container: $docker_container_name" && docker start "$docker_container_name";
done
