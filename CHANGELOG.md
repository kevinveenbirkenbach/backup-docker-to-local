## [1.1.1] - 2025-12-28

* * **Backup:** In ***--dump-only-sql*** mode, fall back to file backups with a warning when no database dump can be produced (e.g. missing `databases.csv` entry).


## [1.1.0] - 2025-12-28

* * **Backup:** Log a warning and skip database dumps when no databases.csv entry is present instead of raising an exception; introduce module-level logging and apply formatting cleanups across backup/restore code and tests.
* **CLI:** Switch to an FHS-compliant default backup directory (/var/lib/backup) and use a stable default repository name instead of dynamic detection.
* **Maintenance:** Update mirror configuration and ignore generated .egg-info files.


## [1.0.0] - 2025-12-27

* Official Release 🥳

