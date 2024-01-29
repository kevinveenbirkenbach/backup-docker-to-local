# Backup Docker Volumes to Local
[![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](./LICENSE.txt)

## goal
This script backups all docker-volumes with the help of rsync.

## scheme
It is part of the following scheme:
![backup scheme](https://www.veen.world/wp-content/uploads/2020/12/server-backup-768x567.jpg)
Further information you will find [in this blog post](https://www.veen.world/2020/12/26/how-i-backup-dedicated-root-servers/).

## Backup all volumes
Execute:

```bash
./backup-docker-to-local.sh
```

## Recover

### database
```bash
  docker exec -i mysql_container mysql -uroot -psecret database < db.sql
```

### volume
Execute:

```bash

bash ./recover-docker-from-local.sh "{{volume_name}}" "$(sha256sum /etc/machine-id | head -c 64)" "{{version_to_recover}}"

```

### Database

## Debug
To checkout what's going on in the mount container type in the following command:

```bash
docker run -it --entrypoint /bin/sh --rm --volumes-from {{container_name}} -v /Backups/:/Backups/ kevinveenbirkenbach/alpine-rsync
```

## Setup
Install pandas

## Author

Kevin Veen-Birkenbach  
- 📧 Email: [kevin@veen.world](mailto:kevin@veen.world)
- 🌍 Website: [https://www.veen.world/](https://www.veen.world/)

## License

This project is licensed under the GNU Affero General Public License v3.0. The full license text is available in the `LICENSE` file of this repository.

## More information
- https://docs.docker.com/storage/volumes/
- https://blog.ssdnodes.com/blog/docker-backup-volumes/
- https://www.baculasystems.com/blog/docker-backup-containers/
- https://gist.github.com/spalladino/6d981f7b33f6e0afe6bb
- https://stackoverflow.com/questions/26331651/how-can-i-backup-a-docker/container/with-its-data-volumes
- https://netfuture.ch/2013/08/simple-versioned-timemachine-like-backup-using-rsync/
- https://zwischenzugs.com/2016/08/29/bash-to-python-converter/
- https://en.wikipedia.org/wiki/Incremental_backup#Incremental
- https://unix.stackexchange.com/questions/567837/linux-backup-utility-for-incremental-backups
- https://chat.openai.com/share/6d10f143-3f7c-4feb-8ae9-5644c3433a65