# docker-volume-backup
[![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](./LICENSE.txt) [![Travis CI](https://api.travis-ci.org/kevinveenbirkenbach/docker-volume-backup.svg?branch=main)](https://travis-ci.org/kevinveenbirkenbach/docker-volume-backup)

## goal
This script backups all docker-volumes with the help of rsync.

## scheme
It is part of the following scheme:
![backup scheme](https://www.veen.world/wp-content/uploads/2020/12/server-backup-768x567.jpg)
Further information you will find [in this blog post](https://www.veen.world/2020/12/26/how-i-backup-dedicated-root-servers/).

## Backup all volumes
Execute:

```bash
./docker-volume-backup.sh
```

## Recover one volume
Execute:

```bash

bash ./docker-volume-recover.sh "{{volume_name}}" "$(sha256sum /etc/machine-id | head -c 64)"

```

## Debug
To checkout what's going on in the mount container type in the following command:

```bash
docker run -it --entrypoint /bin/sh --rm --volumes-from {{container_name}} -v /Backups/:/Backups/ kevinveenbirkenbach/alpine-rsync
```

## Setup
Install pandas

## Optimation
This setup script is not optimized yet for performance. Please optimized this script for performance if you want to use it in a professional environment.

## Stucking rsync
- https://stackoverflow.com/questions/20773118/rsync-suddenly-hanging-indefinitely-during-transfers

## More information
- https://docs.docker.com/storage/volumes/
- https://blog.ssdnodes.com/blog/docker-backup-volumes/
- https://www.baculasystems.com/blog/docker-backup-containers/
- https://gist.github.com/spalladino/6d981f7b33f6e0afe6bb
- https://stackoverflow.com/questions/26331651/how-can-i-backup-a-docker-container-with-its-data-volumes
- https://netfuture.ch/2013/08/simple-versioned-timemachine-like-backup-using-rsync/
- https://zwischenzugs.com/2016/08/29/bash-to-python-converter/
- https://en.wikipedia.org/wiki/Incremental_backup#Incremental
- https://unix.stackexchange.com/questions/567837/linux-backup-utility-for-incremental-backups
