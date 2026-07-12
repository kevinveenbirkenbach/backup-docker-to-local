"""
Bug-repro for: mariadb-dump fails with `ERROR 1045 Access denied for user
'<u>'@'localhost' (using password: YES)` when only '<u>'@'%' is granted and a
preempting ''@'localhost' user is present.

The fix forces TCP loopback in baudolo.backup.db so the dump matches the
'<u>'@'%' grant instead of the socket->localhost auth row.

This file:
- builds the exact preconditions that triggered the production failure,
- as a NEGATIVE control, runs a socket-based mariadb-dump (== the old code path)
  and asserts that it fails with the literal 1045 / @'localhost' error,
- as a POSITIVE proof, calls backup_database() (where the fix lives) against
  the same DB container and asserts the dump file is produced and contains the
  seed data.

Note: the volume-rsync stage of baudolo is intentionally NOT exercised here.
That stage needs root on /var/lib/docker/volumes, which is provided by the
DinD wrapper in `make test-e2e` but not by an on-host invocation. The bug we
are verifying is in the DB-dump stage, so testing backup_database() directly
keeps the assertion focused and the test runnable both on-host and in DinD.
"""

import os
import tempfile
import unittest

import pandas

from baudolo.backup import db as db_mod

from .helpers import (
    MARIADB_IMAGE,
    MARIADB_DATA_DIR,
    cleanup_docker,
    require_docker,
    run,
    unique,
    wait_for_mariadb,
    wait_for_mariadb_sql,
)


class TestE2EMariaDBAnonymousPreemption(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-mariadb-anon")
        cls.db_container = f"{cls.prefix}-mariadb"
        cls.db_volume = f"{cls.prefix}-mariadb-vol"
        cls.containers = [cls.db_container]
        cls.volumes = [cls.db_volume]

        cls.db_name = "appdb"
        cls.db_user = "tcponly"
        cls.db_password = "tcponlypw"
        cls.root_password = "rootpw"

        run(["docker", "volume", "create", cls.db_volume])

        # Boot WITHOUT MARIADB_USER/MARIADB_PASSWORD/MARIADB_DATABASE so the
        # entrypoint does not auto-create '<u>'@'%'. We provision the user
        # explicitly below to mirror the SQL path used by svc-db-mariadb.
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cls.db_container,
                "-e",
                f"MARIADB_ROOT_PASSWORD={cls.root_password}",
                "-v",
                f"{cls.db_volume}:{MARIADB_DATA_DIR}",
                MARIADB_IMAGE,
            ]
        )

        wait_for_mariadb(
            cls.db_container, root_password=cls.root_password, timeout_s=120
        )

        # Provision: '<u>'@'%' (the app/backup grant) + anonymous ''@'localhost'
        # (the preemption trigger). Mirrors the production state that produced
        # `ERROR 1045 ... '<u>'@'localhost' (using password: YES)`.
        bootstrap_sql = (
            f"CREATE DATABASE {cls.db_name};"
            f"CREATE USER '{cls.db_user}'@'%' IDENTIFIED BY '{cls.db_password}';"
            f"GRANT ALL PRIVILEGES ON {cls.db_name}.* TO '{cls.db_user}'@'%';"
            f"CREATE USER ''@'localhost' IDENTIFIED BY 'anonpw-not-{cls.db_password}';"
            "FLUSH PRIVILEGES;"
            f"CREATE TABLE {cls.db_name}.t (id INT PRIMARY KEY, v VARCHAR(50));"
            f"INSERT INTO {cls.db_name}.t VALUES (1,'ok');"
        )
        run(
            [
                "docker",
                "exec",
                cls.db_container,
                "sh",
                "-lc",
                f'mariadb -uroot --protocol=socket -e "{bootstrap_sql}"',
            ]
        )

        # Sanity: '<u>' can log in over TCP (matches '%'). If THIS fails,
        # the precondition for the fix to even apply is broken.
        wait_for_mariadb_sql(
            cls.db_container, user=cls.db_user, password=cls.db_password, timeout_s=60
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    def test_negative_control_socket_dump_fails_with_1045(self) -> None:
        # Reproduces the OLD code path (no -h/--protocol). MUST fail with 1045
        # under the configured preemption. If this ever starts passing, either
        # the MariaDB auth semantics changed or the anonymous-user setup did
        # not take effect — in both cases the positive test below loses its
        # ability to discriminate "fix works" vs "bug never reproduced".
        p = run(
            [
                "docker",
                "exec",
                self.db_container,
                "sh",
                "-lc",
                f"mariadb-dump -u{self.db_user} -p{self.db_password} {self.db_name}",
            ],
            capture=True,
            check=False,
        )
        self.assertNotEqual(p.returncode, 0, "socket-based dump unexpectedly succeeded")
        self.assertIn("1045", (p.stderr or "") + (p.stdout or ""))
        self.assertIn("@'localhost'", (p.stderr or "") + (p.stdout or ""))

    def test_backup_database_succeeds_with_tcp_fix(self) -> None:
        # Drives the function where the fix lives. No rsync, no privileged
        # paths — just the dump that the negative-control proved is failing
        # under the same preemption setup.
        with tempfile.TemporaryDirectory() as volume_dir:
            df = pandas.DataFrame(
                [(self.db_container, self.db_name, self.db_user, self.db_password)],
                columns=["instance", "database", "username", "password"],
            )
            produced = db_mod.backup_database(
                container=self.db_container,
                volume_dir=volume_dir,
                db_type="mariadb",
                databases_df=df,
                database_containers=[self.db_container],
            )
            self.assertTrue(produced, "backup_database did not produce a dump")
            dump_path = os.path.join(volume_dir, "sql", f"{self.db_name}.backup.sql")
            self.assertTrue(os.path.isfile(dump_path), f"expected dump at {dump_path}")
            with open(dump_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            self.assertIn("INSERT INTO", content)
            self.assertIn("'ok'", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
