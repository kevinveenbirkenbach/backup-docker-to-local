# Changelog

## [3.1.0] - 2026-07-15

- Restore: the postgres *--empty* pre-clean emits one DROP per object and
  runs them via *\gexec* instead of a single DO-block, so large schemas
  (e.g. gitlab) no longer exhaust *max_locks_per_transaction* in one
  transaction. It also drops user-owned non-public schemas, so dumps that
  CREATE SCHEMA (e.g. discourse's *discourse_functions*) no longer abort
  on the already-existing schema under ON_ERROR_STOP.
- Backup: *--database-containers* and *--images-no-stop-required* are now
  optional and default to an empty list, so a pure file backup needs no
  dummy arguments; an empty stop whitelist keeps the conservative
  stop-all behavior.
- Tests: new e2e test restores *--empty* against a fully populated
  database containing a non-public schema and every dropped object class.
  *make test* runs the three suites concurrently after a single
  clean+build; *E2E_TEST_PATTERN* runs an e2e subset.

## [3.0.0] - 2026-07-12

- Backup: *--images-no-stop-required* and *--images-no-backup-required* now
  match a container's exact *.Config.Image* (full *repo:tag*, registry
  prefix included) instead of a substring, so a near-miss image name no
  longer flips the stop/skip decision. Callers must pass exact image
  references. **Breaking.**
- Backup: renamed *--hard-compose-restart* to *--hard-restart-projects*
  (its value stays a list of compose project dir names). **Breaking:** the
  old flag name is removed.

## [2.0.0] - 2026-07-12

- Backup: renamed *--docker-compose-hard-restart-required* to
  *--hard-compose-restart* and changed its default from *["mailu"]* to *[]*
  (nargs="*"). The compose down/up is now opt-in: compose hosts pass
  *mailu* explicitly, while swarm hosts pass nothing, since there the dir is
  a stack whose overlay network collides with *compose up*. **Breaking:** the
  old flag name is removed and the implicit mailu default is gone.
- Backup: *--backups-dir* is now required (no */var/lib/backup/* default) so
  a run can never silently target the wrong backup root. **Breaking.**
- Restore: volume files are rsynced directly into the target volume's
  mountpoint (resolved via *docker volume inspect*), mirroring the backup
  path; the *alpine-rsync* helper image and the *--rsync-image* flag are
  gone. The caller needs write access to the docker volume root (root on the
  host, baudolo's normal privilege). **Breaking:** the restore *files*
  subcommand no longer accepts *--rsync-image*.
- Tests: the e2e suite tracks *postgres:alpine* (18+, mounted at
  */var/lib/postgresql*) and *mariadb:latest* from a single source of truth.

## [1.8.1] - 2026-07-12

- Restore: the postgres empty mode also drops user-owned collations in
  public; dumps containing CREATE COLLATION (e.g. OpenProject's ICU
  collation versions_name) no longer abort the replay with 'collation
  already exists'.
- Maintenance: base image bumped from python 3.11-slim to 3.14-slim.

## [1.8.0] - 2026-07-11

Swarm-aware backups and replayable restores.

- Backup: swarm task containers are never stopped or started manually
  anymore; they are skipped visibly and backed up hot, while the sql dump
  stays the consistent database backup.
- Backup: a container that vanishes between listing and inspect no longer
  aborts the run; a failing inspect on a container that still exists keeps
  failing loudly.
- Backup: pg_dump runs with the no-owner and no-privileges flags so dumps
  are replayable by the owning app user.
- Restore: the mariadb empty mode drops all tables in one client session
  with FOREIGN_KEY_CHECKS disabled; FK-linked parent tables no longer abort
  the replay with ERROR 1451.
- Restore: the postgres empty mode drops only current-user-owned objects,
  and the replay skips superuser-only dump lines without ever touching
  COPY data blocks.
- Restore: the replay streams the dump through a temp file instead of
  buffering it in memory; multi-GB dumps no longer OOM the restore.
- Tooling: the e2e runner reaches the DinD daemon via docker exec instead
  of a host-published unencrypted API port.
- Tooling: new end-to-end test reproducing the swarm stop flake, plus unit
  tests for the restore filters and the swarm probes; the suite is 36 unit,
  9 integration and 30 e2e tests.
- Tooling: Dependabot with auto-merge for minor and patch updates.

## [1.7.1] - 2026-05-26

* 🔌 MariaDB SQL backups now connect over TCP loopback so the dump always matches the same wildcard-host grant the application uses — no more surprise `ERROR 1045 Access denied` when a localhost-bound auth row preempts.
* 🧪 New regression and bug-repro tests pin the TCP behaviour and prove it under the exact preemption setup that caused the production failure on MariaDB 12.
* 🩺 E2E test infrastructure: DinD bridge and inner daemon now default to MTU 1280 so registry pulls survive host paths with broken PMTUD (override via `E2E_DIND_MTU`).


## [1.7.0] - 2026-02-07

* 🚀 Backup jobs now support all valid Docker Compose file names – case-insensitive and hassle-free.


## [1.6.0] - 2026-02-06

* Compose handling is now fully delegated to the Infinito.Nexus compose wrapper or plain docker compose, removing all custom env and file detection to ensure a single, consistent source of truth.


## [1.5.0] - 2026-01-31

* * Make `databases.csv` optional: missing or empty files now emit warnings and no longer break backups
* Fix Docker CLI compatibility by switching to `docker-ce-cli` and required build tools


## [1.4.0] - 2026-01-31

* Baudolo now restarts Docker Compose stacks in a wrapper-aware way (with a `docker compose` fallback), ensuring that all Compose overrides and env files are applied identically to the Infinito.Nexus workflow.


## [1.3.0] - 2026-01-10

* Empty databases.csv no longer causes baudolo-seed to fail


## [1.2.0] - 2025-12-29

* * Introduced **`--dump-only-sql`** mode for reliable, SQL-only database backups (replaces `--dump-only`).
* Database configuration in `databases.csv` is now **strict and explicit** (`*` or concrete database name only).
* **PostgreSQL cluster backups** are supported via `*`.
* SQL dumps are written **atomically** to avoid corrupted or empty files.
* Backups are **smarter and faster**: ignored volumes are skipped early, file backups run only when needed.
* Improved reliability through expanded end-to-end tests and safer defaults.


## [1.1.1] - 2025-12-28

* * **Backup:** In ***--dump-only-sql*** mode, fall back to file backups with a warning when no database dump can be produced (e.g. missing `databases.csv` entry).


## [1.1.0] - 2025-12-28

* * **Backup:** Log a warning and skip database dumps when no databases.csv entry is present instead of raising an exception; introduce module-level logging and apply formatting cleanups across backup/restore code and tests.
* **CLI:** Switch to an FHS-compliant default backup directory (/var/lib/backup) and use a stable default repository name instead of dynamic detection.
* **Maintenance:** Update mirror configuration and ignore generated .egg-info files.


## [1.0.0] - 2025-12-27

* Official Release 🥳

