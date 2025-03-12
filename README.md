# Backup Docker Volumes to Local (baudolo) 📦🔄
[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub%20Sponsors-blue?logo=github)](https://github.com/sponsors/kevinveenbirkenbach) [![Patreon](https://img.shields.io/badge/Support-Patreon-orange?logo=patreon)](https://www.patreon.com/c/kevinveenbirkenbach) [![Buy Me a Coffee](https://img.shields.io/badge/Buy%20me%20a%20Coffee-Funding-yellow?logo=buymeacoffee)](https://buymeacoffee.com/kevinveenbirkenbach) [![PayPal](https://img.shields.io/badge/Donate-PayPal-blue?logo=paypal)](https://s.veen.world/paypaldonate)


**Backup Docker Volumes to Local** is a set of Python and shell scripts that enable you to perform incremental backups of all your Docker volumes using rsync. It is designed to integrate seamlessly with [Kevin's Package Manager](https://github.com/kevinveenbirkenbach/package-manager) under the alias **baudolo**, making it easy to install and manage. The tool supports both file and database recoveries with a clear, automated backup scheme.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0) [![Docker Version](https://img.shields.io/badge/Docker-Yes-blue.svg)](https://www.docker.com) [![Python Version](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org) [![GitHub stars](https://img.shields.io/github/stars/kevinveenbirkenbach/backup-docker-to-local.svg?style=social)](https://github.com/kevinveenbirkenbach/backup-docker-to-local/stargazers)

## 🎯 Goal

This project automates the backup of Docker volumes using incremental backups (rsync) and supports recovering both files and database dumps (MariaDB/PostgreSQL). A robust directory stamping mechanism ensures data integrity, and the tool also handles restarting Docker Compose services when necessary.

## 🚀 Features

- **Incremental Backups:** Uses rsync with `--link-dest` for efficient, versioned backups.
- **Database Backup Support:** Backs up MariaDB and PostgreSQL databases from running containers.
- **Volume Recovery:** Provides scripts to recover volumes and databases from backups.
- **Docker Compose Integration:** Option to automatically restart Docker Compose services after backup.
- **Flexible Configuration:** Easily integrated with your Docker environment with minimal setup.
- **Comprehensive Logging:** Detailed command output and error handling for safe operations.

## 🛠 Requirements

- **Linux Operating System** (with Docker installed) 🐧
- **Python 3.x** 🐍
- **Docker & Docker Compose** 🔧
- **rsync** installed on your system

## 📥 Installation

You can install **Backup Docker Volumes to Local** easily via [Kevin's Package Manager](https://github.com/kevinveenbirkenbach/package-manager) using the alias **baudolo**:

```bash
pkgman install baudolo
```

Alternatively, clone the repository directly:

```bash
git clone https://github.com/kevinveenbirkenbach/backup-docker-to-local.git
cd backup-docker-to-local
```

## 🚀 Usage

### Backup All Volumes

To backup all Docker volumes, simply run:

```bash
./backup-docker-to-local.sh
```

### Recovery

#### Recover Volume Files

```bash
bash ./recover-docker-from-local.sh "{{volume_name}}" "$(sha256sum /etc/machine-id | head -c 64)" "{{version_to_recover}}"
```

#### Recover Database

For example, to recover a MySQL/MariaDB database:

```bash
docker exec -i mysql_container mysql -uroot -psecret database < db.sql
```

#### Debug Mode

To inspect what’s happening inside a container:

```bash
docker run -it --entrypoint /bin/sh --rm --volumes-from {{container_name}} -v /Backups/:/Backups/ kevinveenbirkenbach/alpine-rsync
```

## 🔍 Backup Scheme

The backup mechanism uses incremental backups with rsync and stamps directories with a unique hash. For more details on the backup scheme, check out [this blog post](https://blog.veen.world/blog/2020/12/26/how-i-backup-dedicated-root-servers/).  
![Backup Scheme](https://blog.veen.world/wp-content/uploads/2020/12/server-backup-1024x755.jpg)

## 🧑‍💻 Setup & Dependencies

Make sure you have **pandas** installed:

```bash
pip install pandas
```

Also, ensure your system meets all the requirements listed above.

## 👨‍💻 Author

**Kevin Veen-Birkenbach**  
- 📧 [kevin@veen.world](mailto:kevin@veen.world)  
- 🌐 [https://www.veen.world/](https://www.veen.world/)

## 📜 License

This project is licensed under the **GNU Affero General Public License v3.0**. See the [LICENSE](./LICENSE) file for details.

## 🔗 More Information

- [Docker Volumes Documentation](https://docs.docker.com/storage/volumes/)
- [Docker Backup Volumes Blog](https://blog.ssdnodes.com/blog/docker-backup-volumes/)
- [Backup Strategies](https://en.wikipedia.org/wiki/Incremental_backup#Incremental)

---

Happy Backing Up! 🚀🔐
