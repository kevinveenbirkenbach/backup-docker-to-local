# baudolo – Deterministic Backup & Restore for Docker Volumes 📦🔄
[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub%20Sponsors-blue?logo=github)](https://github.com/sponsors/kevinveenbirkenbach) [![Patreon](https://img.shields.io/badge/Support-Patreon-orange?logo=patreon)](https://www.patreon.com/c/kevinveenbirkenbach) [![Buy Me a Coffee](https://img.shields.io/badge/Buy%20me%20a%20Coffee-Funding-yellow?logo=buymeacoffee)](https://buymeacoffee.com/kevinveenbirkenbach) [![PayPal](https://img.shields.io/badge/Donate-PayPal-blue?logo=paypal)](https://s.veen.world/paypaldonate) [![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0) [![Docker Version](https://img.shields.io/badge/Docker-Yes-blue.svg)](https://www.docker.com) [![Python Version](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org) [![GitHub stars](https://img.shields.io/github/stars/kevinveenbirkenbach/backup-docker-to-local.svg?style=social)](https://github.com/kevinveenbirkenbach/backup-docker-to-local/stargazers)


`baudolo` is a backup and restore system for Docker volumes with
**mandatory file backups** and **explicit, deterministic database dumps**.
It is designed for environments with many Docker services where:
- file-level backups must always exist
- database dumps must be intentional, predictable, and auditable

## ✨ Key Features

- 📦 Incremental Docker volume backups using `rsync --link-dest`
- 🗄 Optional SQL dumps for:
  - PostgreSQL
  - MariaDB / MySQL
- 🌱 Explicit database definition for SQL backups (no auto-discovery)
- 🧾 Backup integrity stamping via `dirval` (Python API)
- ⏸ Automatic container stop/start when required for consistency
- 🚫 Whitelisting of containers that do not require stopping
- ♻️ Modular, maintainable Python architecture


## 🧠 Core Concept (Important!)

`baudolo` **separates file backups from database dumps**.

- **Docker volumes are always backed up at file level**
- **SQL dumps are created only for explicitly defined databases**

This results in the following behavior:

| Database defined | File backup | SQL dump |
|------------------|-------------|----------|
| No               | ✔ yes       | ✘ no     |
| Yes              | ✔ yes       | ✔ yes    |

## 📁 Backup Layout

Backups are stored in a deterministic, fully nested structure:

```text
<backups-dir>/
└── <machine-hash>/
    └── <repo-name>/
        └── <timestamp>/
            └── <volume-name>/
                ├── files/
                └── sql/
                    └── <database>.backup.sql
```

### Meaning of each level

* `<machine-hash>`
  SHA256 hash of `/etc/machine-id` (host separation)

* `<repo-name>`
  Logical backup namespace (project / stack)

* `<timestamp>`
  Backup generation (`YYYYMMDDHHMMSS`)

* `<volume-name>`
  Docker volume name

* `files/`
  Incremental file backup (rsync)

* `sql/`
  Optional SQL dumps (only for defined databases)

## 🚀 Installation

### Local (editable install)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 🌱 Database Definition (SQL Backup Scope)

### How SQL backups are defined

`baudolo` creates SQL dumps **only** for databases that are **explicitly defined**
via configuration (e.g. a databases definition file or seeding step).

If a database is **not defined**:

* its Docker volume is still backed up (files)
* **no SQL dump is created**

> No database definition → file backup only
> Database definition present → file backup + SQL dump

### Why explicit definition?

`baudolo` does **not** inspect running containers to guess databases.

Databases must be explicitly defined to guarantee:

* deterministic backups
* predictable restore behavior
* reproducible environments
* zero accidental production data exposure

### Required database metadata

Each database definition provides:

* database instance (container or logical instance)
* database name
* database user
* database password

This information is used by `baudolo` to execute
`pg_dump`, `pg_dumpall`, or `mariadb-dump`.

## 💾 Running a Backup

```bash
baudolo \
  --compose-dir /srv/docker \
  --databases-csv /etc/baudolo/databases.csv \
  --database-containers central-postgres central-mariadb \
  --images-no-stop-required alpine postgres mariadb mysql \
  --images-no-backup-required redis busybox
```

### Common Backup Flags

| Flag            | Description                                 |
| --------------- | ------------------------------------------- |
| `--everything`  | Always stop containers and re-run rsync     |
| `--dump-only-sql`| Skip file backups only for DB volumes when dumps succeed; non-DB volumes are still backed up; fallback to files if no dump.    |
| `--shutdown`    | Do not restart containers after backup      |
| `--backups-dir` | Backup root directory (default: `/Backups`) |
| `--repo-name`   | Backup namespace under machine hash         |

## ♻️ Restore Operations

### Restore Volume Files

```bash
baudolo-restore files \
  my-volume \
  <machine-hash> \
  <version> \
  --backups-dir /Backups \
  --repo-name my-repo
```

Restore into a **different target volume**:

```bash
baudolo-restore files \
  target-volume \
  <machine-hash> \
  <version> \
  --source-volume source-volume
```

### Restore PostgreSQL

```bash
baudolo-restore postgres \
  my-volume \
  <machine-hash> \
  <version> \
  --container postgres \
  --db-name appdb \
  --db-password secret \
  --empty
```

### Restore MariaDB / MySQL

```bash
baudolo-restore mariadb \
  my-volume \
  <machine-hash> \
  <version> \
  --container mariadb \
  --db-name shopdb \
  --db-password secret \
  --empty
```

> `baudolo` automatically detects whether `mariadb` or `mysql`
> is available inside the container

## 🔍 Backup Scheme

The backup mechanism uses incremental backups with rsync and stamps directories with a unique hash. For more details on the backup scheme, check out [this blog post](https://blog.veen.world/blog/2020/12/26/how-i-backup-dedicated-root-servers/).  
![Backup Scheme](https://blog.veen.world/wp-content/uploads/2020/12/server-backup-1024x755.jpg)

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
