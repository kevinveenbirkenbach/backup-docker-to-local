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

