#!/bin/bash
volume_name="$1"          # Volume-Name
backup_hash="$2"          # Hashed Machine ID
version="$3"              # version to backup
container="$4"            # optional
mysql_root_password="$5"  # optional
database="$6"             # optional
backup_folder="Backups/$backup_hash/docker-volume-backup/versions/$version/$volume_name"
backup_files="/$backup_folder/files"
backup_sql="/$backup_folder/sql/backup.sql"
echo "Inspect volume $volume_name"
docker volume inspect "$volume_name"
exit_status_volume_inspect=$?
if [ $exit_status_volume_inspect -eq 0 ]; then
    echo "Volume $volume_name allready exists"
  else
    echo "Create volume $volume_name"
    docker volume create "$volume_name"
fi
if [ ! -d "$backup_files" ]; then
  if [ ! -f "$backup_sql" ]; then
    echo "ERROR: $backup_files and $backup_sql don't exist"
    exit 1
  fi
  cat $backup_sql | docker exec -i "$container" '/usr/bin/mysql -u root --password="'$mysql_root_password'" "'$database'"'
fi
docker run --rm -v "$volume_name:/recover/" -v "$backup_files:/backup/" "kevinveenbirkenbach/alpine-rsync" sh -c "rsync -avv --delete /backup/ /recover/"
