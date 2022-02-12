#!/bin/bash
# @param $1 Volume-Name
# @param $2 Hash-Name
volume_name="$1"
backup_hash="$2"
backup_path="/Backups/$backup_hash/docker-volume-backup/latest/$volume_name/files"
echo "Inspect volume $volume_name"
docker volume inspect "$volume_name"
exit_status_volume_inspect=$?
if [ $exit_status_volume_inspect -eq 0 ]; then
    echo "Volume $volume_name allready exists"
  else
    echo "Create volume $volume_name"
    docker volume create "$volume_name"
fi
if [ ! -d "$backup_path" ]; then
  echo "ERROR: $backup_path doesn't exist"
  exit 1
fi
docker run --rm -v "$volume_name:/recover/" -v "$backup_path:/backup/" "kevinveenbirkenbach/alpine-rsync" sh -c "rsync -avv --delete /backup/ /recover/"
