#!/bin/bash
# Just backups volumes of running containers
# If rsync stucks consider:
# @see https://stackoverflow.com/questions/20773118/rsync-suddenly-hanging-indefinitely-during-transfers
#
echo "start backup routine..." &&
echo "start volume backups..." &&
backup_time="$(date '+%Y%m%d%H%M%S')" &&
backups_folder="/Backups/" &&
repository_name="$(cd "$(dirname "$(readlink -f "${0}")")" && basename `git rev-parse --show-toplevel`)" &&
machine_id="$(sha256sum /etc/machine-id | head -c 64)" &&
backup_repository_folder="$backups_folder$machine_id/$repository_name/" || exit 1
for volume_name in $(docker volume ls --format '{{.Name}}')
do
  echo "start backup routine for volume: $volume_name" &&
  containers="$(docker ps --filter volume="$volume_name" --format '{{.Names}}')" &&
  containers_array=($containers) &&
  container=${containers_array[0]} || exit 1
  if [ -z "$containers" ]
    then
      echo "skipped due to no running containers using this volume." || exit 1
    else
      echo "stop containers:" && docker stop $containers || exit 1
      for source_path in $(docker inspect --format "{{ range .Mounts }}{{ if eq .Type \"volume\"}}{{ if eq .Name \"$volume_name\"}}{{ println .Destination }}{{ end }}{{ end }}{{ end }}" "$container");
      do
        destination_path="$backup_repository_folder""latest/$volume_name" &&
        raw_destination_path="$destination_path/raw" &&
        prepared_destination_path="$destination_path/prepared" &&
        log_path="$backup_repository_folder""log.txt" &&
        backup_dir_path="$backup_repository_folder""diffs/$backup_time/$volume_name" &&
        raw_backup_dir_path="$backup_dir_path/raw" &&
        prepared_backup_dir_path="$backup_dir_path/prepared" || exit 1
        if [ -d "$destination_path" ]
          then
            echo "backup volume: $volume_name" || exit 1
          else
            echo "first backup volume: $volume_name" &&
            mkdir -vp "$raw_destination_path" &&
            mkdir -vp "$raw_backup_dir_path" &&
            mkdir -vp "$prepared_destination_path" &&
            mkdir -vp "$prepared_backup_dir_path" || exit 1
        fi
        docker run --rm --volumes-from "$container" -v "$backups_folder:$backups_folder" "kevinveenbirkenbach/alpine-rsync" sh -c "
        rsync -abP --delete --delete-excluded --log-file=$log_path --backup-dir=$raw_backup_dir_path '$source_path/' $raw_destination_path" &&
        echo "start containers:" && docker start $containers || exit 1
      done
  fi
  echo "end backup routine for volume: $volume_name" || exit 1
done
echo "finished volume backups." &&
echo "restart docker service..." &&
systemctl restart docker || exit 1
echo "finished backup routine." || exit 1
