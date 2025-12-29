# tests/e2e/test_e2e_mariadb_no_copy.py
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
    wait_for_mariadb_sql,
)


class TestE2EMariaDBNoCopy(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-mariadb-nocopy")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)
        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        cls.db_container = f"{cls.prefix}-mariadb"
        cls.db_volume = f"{cls.prefix}-mariadb-vol"
        cls.containers = [cls.db_container]
        cls.volumes = [cls.db_volume]

        cls.db_name = "appdb"
        cls.db_user = "test"
        cls.db_password = "testpw"
        cls.root_password = "rootpw"

        run(["docker", "volume", "create", cls.db_volume])

        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cls.db_container,
                "-e",
                f"MARIADB_ROOT_PASSWORD={cls.root_password}",
                "-e",
                f"MARIADB_DATABASE={cls.db_name}",
                "-e",
                f"MARIADB_USER={cls.db_user}",
                "-e",
                f"MARIADB_PASSWORD={cls.db_password}",
                "-v",
                f"{cls.db_volume}:/var/lib/mysql",
                "mariadb:11",
            ]
        )

        wait_for_mariadb(
            cls.db_container, root_password=cls.root_password, timeout_s=90
        )
        wait_for_mariadb_sql(
            cls.db_container, user=cls.db_user, password=cls.db_password, timeout_s=90
        )

        # Create table + data (TCP)
        run(
            [
                "docker",
                "exec",
                cls.db_container,
                "sh",
                "-lc",
                f"mariadb -h 127.0.0.1 -u{cls.db_user} -p{cls.db_password} "
                f'-e "CREATE TABLE {cls.db_name}.t (id INT PRIMARY KEY, v VARCHAR(50)); '
                f"INSERT INTO {cls.db_name}.t VALUES (1,'ok');\"",
            ]
        )

        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"
        write_databases_csv(
            cls.databases_csv,
            [(cls.db_container, cls.db_name, cls.db_user, cls.db_password)],
        )

        # dump-only-sql => no files
        backup_run(
            backups_dir=cls.backups_dir,
            repo_name=cls.repo_name,
            compose_dir=cls.compose_dir,
            databases_csv=cls.databases_csv,
            database_containers=[cls.db_container],
            images_no_stop_required=["mariadb", "mysql", "alpine", "postgres"],
            dump_only_sql=True,
        )

        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

        # Wipe table (TCP)
        run(
            [
                "docker",
                "exec",
                cls.db_container,
                "sh",
                "-lc",
                f"mariadb -h 127.0.0.1 -u{cls.db_user} -p{cls.db_password} "
                f'-e "DROP TABLE {cls.db_name}.t;"',
            ]
        )

        # Restore DB
        run(
            [
                "baudolo-restore",
                "mariadb",
                cls.db_volume,
                cls.hash,
                cls.version,
                "--backups-dir",
                cls.backups_dir,
                "--repo-name",
                cls.repo_name,
                "--container",
                cls.db_container,
                "--db-name",
                cls.db_name,
                "--db-user",
                cls.db_user,
                "--db-password",
                cls.db_password,
                "--empty",
            ]
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    def test_files_backup_not_present(self) -> None:
        p = (
            backup_path(self.backups_dir, self.repo_name, self.version, self.db_volume)
            / "files"
        )
        self.assertFalse(p.exists(), f"Did not expect files backup dir at: {p}")

    def test_data_restored(self) -> None:
        p = run(
            [
                "docker",
                "exec",
                self.db_container,
                "sh",
                "-lc",
                f"mariadb -h 127.0.0.1 -u{self.db_user} -p{self.db_password} "
                f'-N -e "SELECT v FROM {self.db_name}.t WHERE id=1;"',
            ]
        )
        self.assertEqual((p.stdout or "").strip(), "ok")
