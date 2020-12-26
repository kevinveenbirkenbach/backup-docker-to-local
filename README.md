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
