#!/bin/bash

# Check minimum number of arguments
if [ $# -lt 3 ]; then
  echo "ERROR: Not enough arguments. Please provide at least a volume name, backup hash, and version."
  exit 1
fi

volume_name="$1"                # Volume-Name
backup_hash="$2"                # Hashed Machine ID
version="$3"                    # version to recover

# DATABASE PARAMETERS
database_type="$4"              # Valid values; mariadb, postgress
database_container="$5"         # optional
database_password="$6"          # optional
database_name="$7"              # optional
database_user="$database_name"  


backup_folder="Backups/$backup_hash/backup-docker-to-local/$version/$volume_name"
backup_files="/$backup_folder/files"
backup_sql="/$backup_folder/sql/$database_name.backup.sql"

# DATABASE RECOVERY

if [ -f "$backup_sql" ]; then
  if [ "$database_type" = "postgres" ]; then
    if [ -n "$database_container" ] && [ -n "$database_password" ] && [ -n "$database_name" ]; then
      echo "Recover PostgreSQL dump"
      export PGPASSWORD="$database_password"
      cat "$backup_sql" | docker exec -i "$database_container" psql -U "$database_user" -d "$database_name"
      if [ $? -ne 0 ]; then
          echo "ERROR: Failed to recover PostgreSQL dump"
          exit 1
      fi
      exit 0
    fi
  elif [ "$database_type" = "mariadb" ]; then
    if [ -n "$database_container" ] && [ -n "$database_password" ] && [ -n "$database_name" ]; then
      echo "recover mysql dump"
      cat "$backup_sql" | docker exec -i "$database_container" mariadb -u "$database_user" --password="$database_password" "$database_name"
      if [ $? -ne 0 ]; then
          echo "ERROR: Failed to recover mysql dump"
          exit 1
      fi
      exit 0
    fi
  fi
  echo "A database backup exists, but a parameter is missing."
  exit 1
fi

# FILE RECOVERY

echo "Inspect volume $volume_name"
docker volume inspect "$volume_name"
exit_status_volume_inspect=$?

if [ $exit_status_volume_inspect -eq 0 ]; then
    echo "Volume $volume_name already exists"
else
    echo "Create volume $volume_name"
    docker volume create "$volume_name"
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create volume $volume_name"
        exit 1
    fi
fi

if [ -d "$backup_files" ]; then    
  echo "recover files"
  docker run --rm -v "$volume_name:/recover/" -v "$backup_files:/backup/" "kevinveenbirkenbach/alpine-rsync" sh -c "rsync -avv --delete /backup/ /recover/"
  if [ $? -ne 0 ]; then
    echo "ERROR: Failed to recover files"
    exit 1
  fi
  exit 0
else
  echo "ERROR: $backup_files doesn't exist"
  exit 1
fi

echo "ERROR: Unhandled case"
exit 1