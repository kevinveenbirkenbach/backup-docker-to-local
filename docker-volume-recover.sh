#!/bin/bash
# @param $1 Volume-Name
volume_name="$1"
backup_path="$2"
docker volume create "$volume_name"
docker run --rm -v "$volume_name:/recover/" -v "$backup_path:/backup/" "kevinveenbirkenbach/alpine-rsync" sh -c "rsync -avv /backup/ /recover/"
