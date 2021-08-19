#!/bin/bash
# Just backups volumes of running containers
# If rsync stucks consider:
# @see https://stackoverflow.com/questions/20773118/rsync-suddenly-hanging-indefinitely-during-transfers
#
backup_time="$(date '+%Y%m%d%H%M%S')";
backups_folder="/Backups/";
repository_name="$(cd "$(dirname "$(readlink -f "${0}")")" && basename `git rev-parse --show-toplevel`)";
machine_id="$(sha256sum /etc/machine-id | head -c 64)";
backup_repository_folder="$backups_folder$machine_id/$repository_name/";
for volume_name in $(docker volume ls --format '{{.Name}}');
do
  echo "start backup routine: $volume_name";
  for container_name in $(docker ps -a --filter volume=$volume_name --format '{{.Names}}');
  do
    echo "stop container: $container_name" && docker stop "$container_name"
    for source_path in $(docker inspect --format "{{ range .Mounts }}{{ if eq .Type \"volume\"}}{{ if eq .Name \"$volume_name\"}}{{ println .Destination }}{{ end }}{{ end }}{{ end }}" "$container_name");
    do
      destination_path="$backup_repository_folder""latest/$volume_name";
      log_path="$backup_repository_folder""log.txt";
      backup_dir_path="$backup_repository_folder""diffs/$backup_time/$volume_name";
      if [ -d "$destination_path" ]
        then
          echo "backup volume: $volume_name";
        else
          echo "first backup volume: $volume_name"
          mkdir -vp "$destination_path";
          mkdir -vp "$backup_dir_path";
      fi
      docker run --rm --volumes-from "$container_name" -v "$backups_folder:$backups_folder" "kevinveenbirkenbach/alpine-rsync" sh -c "
      rsync -abP --delete --delete-excluded --log-file=$log_path --backup-dir=$backup_dir_path '$source_path/' $destination_path";
    done
    echo "start container: $container_name" && docker start "$container_name";
  done
  echo "end backup routine: $volume_name";
done
