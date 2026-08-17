"""Copy a live database's volume out of a snapshot, using the real backup path.

Runs inside the privileged container built by test_e2e_snapshot_db.py, where a
database is mid-write on a btrfs subvolume. Exercises volume_snapshot and
backup_volume exactly as a backup run would.
"""

from __future__ import annotations

import subprocess
import sys

sys.path.insert(0, "/src")

from baudolo.backup.snapshot import SnapshotError, volume_snapshot
from baudolo.backup.volume import backup_volume

SUBJECT = "/subject/docker"
VOLUME = "mariadb_data"
DATADIR = f"{SUBJECT}/volumes/{VOLUME}/_data"
VERSIONS = "/backups"
GENERATION = f"{VERSIONS}/20260731"


def shell(command: str) -> list[str]:
    proc = subprocess.run(
        command, shell=True, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise SnapshotError(
            f"{command} exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return proc.stdout.splitlines()


with volume_snapshot("btrfs", SUBJECT, "dbtest", run=shell) as resolve:
    backup_volume(
        VERSIONS,
        VOLUME,
        f"{GENERATION}/{VOLUME}",
        authoritative=True,
        source=resolve(f"{DATADIR}/"),
    )

print("SNAPSHOT COPY DONE", flush=True)
