# docker-volume-backup

This script backups all docker-volumes with the help of rsync.

## Backup
Execute:

```bash
./docker-volume-backup.sh
```

## Test
Delete the volume.

```bash
docker rm -f container-name
docker volume rm volume-name
```

Recover the volume:

```bash
docker volume create volume-name
docker run --rm -v volume-name:/recover/ -v ~/backup/:/backup/ "kevinveenbirkenbach/alpine-rsync" sh -c "rsync -avv /backup/ /recover/"
```

Restart the container.

## More information
See https://blog.ssdnodes.com/blog/docker-backup-volumes/.
