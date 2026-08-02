# Changelog

## [3.4.0] - 2026-08-02

- Backup: *-a* implies *-D*, so a generation was written with
  *--devices --specials* and rsync recreated every unix socket and fifo found in
  a volume. Where the backup root is an nfs-ganesha export, ganesha accepts the
  socket on write but cannot serve it back, and the remote pull's sender then
  fails with *readdir* / *readlink_stat* "Invalid argument (22)" and exits 23 —
  deterministically, for every retry. *--no-D* keeps them out of the generation.
- Backup: nothing restorable is lost. Sockets and fifos are recreated by the
  daemons that own them, and the postfix queue itself — *incoming*, *active*,
  *deferred*, *hold*, *maildrop* — is unaffected, so accepted-but-undelivered
  mail stays in the backup. Device nodes go too; the only volume that could hold
  them is a nested docker data root, which does not belong in a backup anyway.
- Tests: the flag is asserted on the rsync invocation.

## [3.3.0] - 2026-08-02

- Backup: *--volumes-no-backup-required* excludes a volume by name.
  *--images-no-backup-required* resolves through *volume_is_fully_ignored*,
  which skips a volume only when every container using it is ignored — a
  container holding a derived tree beside state that must be kept cannot
  express the exclusion at all. A docker-in-docker data root is exactly that
  shape, and excluding by image would drop all three of its volumes.
- Backup: the name check runs before *containers_using_volume*, so an excluded
  volume costs no docker inspection and the decision does not depend on which
  containers exist when the run starts.
- Tests: two volumes off one container, asserting the sibling survives — the
  property the image lever cannot provide — as unit and end-to-end.

## [3.2.2] - 2026-07-31

- Backup: the btrfs snapshot is carved inside its subject, as
  *<data root>/.baudolo-<tag>*, not beside it. The kernel refuses a snapshot
  whose destination is on another filesystem, which is exactly what the parent
  directory is when the data root is a mountpoint of its own — a dedicated disk
  mounted onto */var/lib/docker* failed every run with EXDEV. Placing it inside
  makes source and destination the same filesystem by construction, and aligns
  btrfs with the zfs path, which already resolves its snapshot inside the
  subject at *<subject>/.zfs/snapshot/<tag>*. A leftover from an interrupted run
  appears in the next snapshot as an empty directory rather than recursing,
  since btrfs does not include nested subvolumes.

## [3.2.1] - 2026-07-31

- Backup: the snapshot resolver keeps the trailing separator *get_storage_path*
  puts on a volume path — *os.path.abspath* stripped it. rsync reads *dir* as
  "copy the directory" where *dir/* means "copy its contents", so every snapshot
  generation landed at *<volume>/files/_data/...* while the live path lands at
  *<volume>/files/...*. Restores read the live layout, and *--link-dest* had
  nothing to match against the previous generation.
- Backup: snapshot teardown no longer fails a completed run. A busy
  *btrfs subvolume delete* raised out of the *finally*, skipping the generation
  stamp and the compose handling on a run whose data was already copied, and
  masking whatever the body had raised. The leftover is reported instead.
- Backup: a volume created after the snapshot was taken is copied live with a
  warning instead of aborting the run. Nothing is stopped in snapshot mode, so
  the host keeps creating volumes for the whole copy.
- Backup: the snapshot pass compares by content (*--checksum*) again. 3.2.0
  dropped it because a snapshot source cannot move, which is true, but the
  comparison that matters is against *--link-dest*: a file that changed while
  keeping its size and whole-second mtime was hard-linked stale out of the
  previous generation, and the single pass had no authoritative pass to repair
  it. Still one pass where the live path takes two.
- Backup: *--hard-restart-projects* is refused alongside *--snapshot*, like
  *--shutdown* already is. It exists for stacks whose database cannot be backed
  up hot, which is what a snapshot removes.
- Tests: the trailing separator, both teardown behaviours, the new refusal, and
  *app.main* driving the snapshot branch — the caller that runs in production,
  which no test had exercised, which is why the layout defect shipped.

## [3.2.0] - 2026-07-31

- Backup: *--snapshot {btrfs,zfs}* with *--snapshot-subject* captures every
  volume from one atomic filesystem snapshot. The subject — the btrfs subvolume
  or zfs dataset holding the docker volumes, e.g. */var/lib/docker* — is frozen
  once per run, so a generation shares a single point in time and no container
  is stopped. Restoring such a copy is an ordinary crash recovery, which every
  supported engine performs at startup. This is the mode 3.1.4 pointed to for
  volumes where two rsync passes over a live tree stop being affordable.
- Backup: snapshot passes copy once and drop *--checksum*. Verification exists
  because a hot pass writes its destination from a moving source; a snapshot
  source cannot move, so size and mtime cannot race and the second full read is
  pure cost.
- Backup: an unsupported filesystem or unknown kind fails with *SnapshotError*.
  The kind is stated, not probed — an inconclusive probe would fall back to a
  live copy and hand out the torn backup the mode prevents. *--shutdown* is
  rejected alongside *--snapshot* rather than ignored, since nothing is stopped.
- Refactor: *backup/app.py* splits into *layout.py*, *policy.py* and *dumps.py*
  along the lines it already had; 276 lines down to 124.
- Tests: unit coverage for snapshot, layout, policy, volume and CLI validation.
  E2E cases drive real btrfs, zfs and ext4 on loop devices, one proving the
  loud refusal; another writes a MariaDB across the snapshot and requires the
  restored server to recover on its own with every committed row and none of
  the later ones. CI installs zfs and sets *E2E_REQUIRE_FILESYSTEMS*, so a
  missing kernel module fails the build instead of skipping a filesystem.

## [3.1.4] - 2026-07-31

- Backup: the post-stop volume pass now compares by content (*--checksum*), so
  it can no longer skip a file the hot pass had copied from a live source. Each
  volume is rsynced twice into the same destination — once with the container
  running, once after it is stopped — and the second pass used rsync's quick
  check (size plus whole-second mtime). A pre-allocated 16 MiB WAL segment never
  changes size, so when its last pre-stop write and postgres' shutdown
  checkpoint fell in the same whole second, the cold pass skipped it while still
  replacing *global/pg_control*, whose previous write was seconds earlier. The
  generation then paired a post-shutdown *pg_control* with a WAL segment still
  zeroed at the recorded checkpoint LSN, and restoring it crash-looped postgres
  with "invalid record length … expected at least 24, got 0" followed by "PANIC:
  could not locate a valid checkpoint record". *backup_volume* takes
  *authoritative* as a required keyword rather than an optional flag, so each of
  the four call sites states which pass it is; the hot passes keep the quick
  check. *--ignore-times* was rejected because it destroys the *--link-dest*
  hardlink dedup (measured 20/20 to 0/20, generation size doubled), and
  *--modify-window=-1* because it makes correctness depend on the destination
  filesystem preserving sub-second mtimes, which degrades silently on NFS or
  ext3.
- Cost: the quick check scales with file count, *--checksum* with bytes read on
  both sides, and it runs while the container is stopped. The extra stop time
  stays under a minute up to roughly 4 GB on spinning disk, 15 GB on a SATA SSD
  and 60 GB on NVMe; at 1 TB it is 17 minutes on NVMe and over three hours on
  spinning disk. No size threshold is built in, since a guessed one would drop
  the guarantee exactly where an unrestorable backup costs most — volumes at
  that scale want filesystem snapshots or *pg_basebackup* rather than two rsync
  passes over a live tree.

## [3.1.3] - 2026-07-20

- Restore: the postgres dump replay now runs under *--single-transaction*,
  so a concurrent writer on a live database can no longer interleave a row
  between the replay's table re-create and its *COPY* and trip a "duplicate
  key value violates unique constraint" abort under ON_ERROR_STOP. This is
  the discourse restore-drill race (*mini_scheduler* upserting
  *scheduler_stats(id=1)* mid-restore) that failed the whole restore. The
  *--empty* pre-clean stays multi-statement (*\gexec*, one DROP per
  statement) because a single DROP transaction exhausts
  *max_locks_per_transaction* on large schemas (e.g. gitlab).
- Refactor: the *--empty* pre-clean SQL moves out of the inline Python
  string into *src/baudolo/restore/db/empty_preclean.sql* (loaded via
  *dirname(__file__)*, declared as package-data so it ships in the wheel).
- Tests: a unit test guards the single-transaction / multi-statement split
  (replay carries *--single-transaction*, pre-clean does not); a new e2e
  reproduces the live-writer race and asserts the restore survives it.

## [3.1.2] - 2026-07-18

- Restore: the postgres *--empty* pre-clean also drops user-owned text
  search configurations and dictionaries (*pg_ts_config*, *pg_ts_dict*),
  so a schema shipping a custom dictionary (e.g. taiga's
  *english_stem_nostop*) no longer aborts the replay with "duplicate key
  value violates unique constraint pg_ts_dict_dictname_index" under
  ON_ERROR_STOP.
- Tests: the string-assertion unit test for the pre-clean SQL is replaced
  by real scenario data in the e2e: the seeded schema contains an
  overloaded *f()/f(int)* pair and the nostop dictionary plus
  configuration, and the restored database is queried to prove each
  survives the backup, pre-clean and replay cycle exactly once.

## [3.1.1] - 2026-07-17

- Restore: the postgres *--empty* pre-clean drops functions and procedures
  by their identity signature (*pg_get_function_identity_arguments*), so a
  schema that overloads a function name (e.g. discourse) no longer aborts
  the replay with "function name is not unique" under ON_ERROR_STOP.
  Identifier quoting moves from the outer DROP format into each object
  branch, since the *name(args)* compound must not be quoted as a whole; a
  unit test pins the per-branch *%I* quoting so future branches cannot
  regress unquoted.

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

