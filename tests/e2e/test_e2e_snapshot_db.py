"""A live database survives being captured from a snapshot.

The database is written to while the snapshot is taken and keeps writing
afterwards, so the copy can only be a point in time - never a clean shutdown.
A second server is then started on that copy: it must recover on its own and
still hold every row committed before the snapshot.
"""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from .helpers import require_docker, run, unique

REPO_SRC = Path(__file__).resolve().parents[2] / "src"
DRIVER = Path(__file__).resolve().parent / "snapshot_db_driver.py"
IMAGE = "alpine:3.20"
SOCKET = "/tmp/live.sock"
RESTORED_SOCKET = "/tmp/restored.sock"
DATADIR = "/subject/docker/volumes/mariadb_data/_data"
RESTORED = "/restored"

SCRIPT = f"""set -e
apk add -q btrfs-progs util-linux python3 mariadb mariadb-client rsync
truncate -s 900M /img
mkfs.btrfs -q /img
mkdir -p /subject
LOOP=$(losetup -f | awk '{{print $1}}')
{{ [ -b "$LOOP" ] || mknod "$LOOP" b 7 "${{LOOP#/dev/loop}}"; }}
losetup "$LOOP" /img
mount -t btrfs "$LOOP" /subject
btrfs subvolume create /subject/docker >/dev/null
mkdir -p {DATADIR}

mariadb-install-db --user=root --datadir={DATADIR} >/dev/null 2>&1
mariadbd --user=root --datadir={DATADIR} --socket={SOCKET} --skip-networking &
for i in $(seq 1 60); do mariadb-admin --socket={SOCKET} ping >/dev/null 2>&1 && break; sleep 1; done

mariadb --socket={SOCKET} -e "CREATE DATABASE demo;
  CREATE TABLE demo.t (id INT PRIMARY KEY, v VARCHAR(32)) ENGINE=InnoDB;
  INSERT INTO demo.t VALUES (1,'committed'),(2,'committed');"

mariadb --socket={SOCKET} -e "INSERT INTO demo.t VALUES (3,'committed');"
python3 /driver.py
mariadb --socket={SOCKET} -e "INSERT INTO demo.t VALUES (4,'after-snapshot');"

mkdir -p {RESTORED}
rsync -a /backups/20260731/mariadb_data/files/ {RESTORED}/
mariadbd --user=root --datadir={RESTORED} --socket={RESTORED_SOCKET} --skip-networking &
for i in $(seq 1 60); do mariadb-admin --socket={RESTORED_SOCKET} ping >/dev/null 2>&1 && break; sleep 1; done

echo "RESTORED_ROWS=$(mariadb --socket={RESTORED_SOCKET} -N -B -e 'SELECT COUNT(*) FROM demo.t;')"
echo "RESTORED_AFTER=$(mariadb --socket={RESTORED_SOCKET} -N -B -e \\
  "SELECT COUNT(*) FROM demo.t WHERE v='after-snapshot';")"
echo DB_OK
"""


class TestE2ESnapshotDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        staged = Path("/tmp") / unique("baudolo-e2e-snapshot-db")
        shutil.copytree(REPO_SRC, staged / "src")
        shutil.copy(DRIVER, staged / "driver.py")
        try:
            proc = run(
                [
                    "docker", "run", "--rm", "--privileged",
                    "--name", staged.name,
                    "-v", f"{staged / 'src'}:/src:ro",
                    "-v", f"{staged / 'driver.py'}:/driver.py:ro",
                    IMAGE, "sh", "-lc", SCRIPT,
                ],
                capture=True,
                check=False,
            )
        finally:
            shutil.rmtree(staged, ignore_errors=True)
        cls.output = proc.stdout + proc.stderr
        cls.returncode = proc.returncode

    def test_the_run_completed(self) -> None:
        self.assertEqual(self.returncode, 0, self.output)
        self.assertIn("DB_OK", self.output)

    def test_the_backup_came_from_the_snapshot(self) -> None:
        self.assertIn("SNAPSHOT COPY DONE", self.output)

    def test_the_restored_server_recovered_on_its_own(self) -> None:
        self.assertIn("RESTORED_ROWS=3", self.output)

    def test_writes_after_the_snapshot_are_absent(self) -> None:
        self.assertIn("RESTORED_AFTER=0", self.output)

    def test_the_copy_was_an_unclean_state_the_engine_had_to_repair(self) -> None:
        self.assertRegex(self.output, r"(?i)crash recovery|rolling back|log sequence")


if __name__ == "__main__":
    unittest.main()
