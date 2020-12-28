# docker-volume-backup
[![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](./LICENSE.txt) [![Travis CI](https://travis-ci.org/kevinveenbirkenbach/docker-volume-backup.svg?branch=master)](https://travis-ci.org/kevinveenbirkenbach/docker-volume-backup)

## goal
This script backups all docker-volumes with the help of rsync.

## scheme
It is part of the following scheme:
![backup scheme](https://www.veen.world/wp-content/uploads/2020/12/server-backup-768x567.jpg)
Further information you will find [in this blog post](https://www.veen.world/2020/12/26/how-i-backup-dedicated-root-servers/).

## Backup
Execute:

```bash
./docker-volume-backup.sh
```

## Debug
To checkout what's going on in the mount container type in the following command:

```bash
docker run -it --entrypoint /bin/sh --rm --volumes-from {{container_name}} -v /Backups/:/Backups/ kevinveenbirkenbach/alpine-rsync
```
## Manual Backup
rsync -aPvv  '***{{source_path}}***/' ***{{destination_path}}***";

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

## Optimation
This setup script is not optimized yet for performance. Please optimized this script for performance if you want to use it in a professional environment.

## More information
- https://blog.ssdnodes.com/blog/docker-backup-volumes/
- https://www.baculasystems.com/blog/docker-backup-containers/
