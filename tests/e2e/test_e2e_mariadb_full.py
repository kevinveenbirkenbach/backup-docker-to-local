# tests/e2e/test_e2e_mariadb_full.py
import unittest

from .helpers import (
    backup_run,
    backup_path,
    cleanup_docker,
    create_minimal_compose_dir,
    ensure_empty_dir,
    latest_version_dir,
    require_docker,
    unique,
    write_databases_csv,
    run,
    wait_for_mariadb,
)


class TestE2EMariaDBFull(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-mariadb-full")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)
        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        cls.db_container = f"{cls.prefix}-mariadb"
        cls.db_volume = f"{cls.prefix}-mariadb-vol"
        cls.containers = [cls.db_container]
        cls.volumes = [cls.db_volume]

        run(["docker", "volume", "create", cls.db_volume])

        # Start MariaDB (no host port publishing needed; we will exec into the container)
        run([
            "docker", "run", "-d",
            "--name", cls.db_container,
            "-e", "MARIADB_ROOT_PASSWORD=rootpw",
            "-v", f"{cls.db_volume}:/var/lib/mysql",
            "mariadb:11",
        ])
        wait_for_mariadb(cls.db_container, root_password="rootpw", timeout_s=90)

        # Create DB + data
        run([
            "docker", "exec", cls.db_container,
            "sh", "-lc",
            "mariadb -uroot -prootpw -e \"CREATE DATABASE appdb; "
            "CREATE TABLE appdb.t (id INT PRIMARY KEY, v VARCHAR(50)); "
            "INSERT INTO appdb.t VALUES (1,'ok');\"",
        ])

        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        instance = cls.db_container
        write_databases_csv(cls.databases_csv, [(instance, "appdb", "root", "rootpw")])

        # Backup with file+dump
        backup_run(
            backups_dir=cls.backups_dir,
            repo_name=cls.repo_name,
            compose_dir=cls.compose_dir,
            databases_csv=cls.databases_csv,
            database_containers=[cls.db_container],
            images_no_stop_required=["mariadb", "mysql", "alpine", "postgres"],
        )

        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

        # Wipe DB
        run([
            "docker", "exec", cls.db_container,
            "sh", "-lc",
            "mariadb -uroot -prootpw -e \"DROP DATABASE appdb;\"",
        ])

        # Restore DB
        run([
            "baudolo-restore", "mariadb",
            cls.db_volume, cls.hash, cls.version,
            "--backups-dir", cls.backups_dir,
            "--repo-name", cls.repo_name,
            "--container", cls.db_container,
            "--db-name", "appdb",
            "--db-user", "root",
            "--db-password", "rootpw",
            "--empty",
        ])

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    def test_dump_file_exists(self) -> None:
        p = backup_path(self.backups_dir, self.repo_name, self.version, self.db_volume) / "sql" / "appdb.backup.sql"
        self.assertTrue(p.is_file(), f"Expected dump file at: {p}")

    def test_data_restored(self) -> None:
        p = run([
            "docker", "exec", self.db_container,
            "sh", "-lc",
            "mariadb -uroot -prootpw -N -e \"SELECT v FROM appdb.t WHERE id=1;\"",
        ])
        self.assertEqual((p.stdout or "").strip(), "ok")
