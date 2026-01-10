import unittest

from .helpers import (
    backup_path,
    cleanup_docker,
    create_minimal_compose_dir,
    ensure_empty_dir,
    latest_version_dir,
    require_docker,
    run,
    unique,
    wait_for_postgres,
)


class TestE2ESeedStarAndDbEntriesBackupPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()

        cls.prefix = unique("baudolo-e2e-seed-star-and-db")
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        ensure_empty_dir(cls.backups_dir)

        cls.compose_dir = create_minimal_compose_dir(f"/tmp/{cls.prefix}")
        cls.repo_name = cls.prefix

        # --- Volumes ---
        cls.db_volume = f"{cls.prefix}-vol-db"
        cls.files_volume = f"{cls.prefix}-vol-files"
        cls.volumes = [cls.db_volume, cls.files_volume]

        run(["docker", "volume", "create", cls.db_volume])
        run(["docker", "volume", "create", cls.files_volume])

        # Put a marker into the non-db volume
        cls.marker = "hello-non-db-seed-star"
        run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{cls.files_volume}:/data",
                "alpine:3.20",
                "sh",
                "-lc",
                f"echo '{cls.marker}' > /data/hello.txt",
            ]
        )

        # --- Start Postgres container using the DB volume ---
        cls.pg_container = f"{cls.prefix}-pg"
        cls.containers = [cls.pg_container]

        cls.pg_password = "postgres"
        cls.pg_user = "postgres"

        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cls.pg_container,
                "-e",
                f"POSTGRES_PASSWORD={cls.pg_password}",
                "-v",
                f"{cls.db_volume}:/var/lib/postgresql/data",
                "postgres:16-alpine",
            ]
        )
        wait_for_postgres(cls.pg_container, user="postgres", timeout_s=90)

        # Create two DBs and deterministic content, so pg_dumpall is meaningful
        cls.pg_db1 = "testdb1"
        cls.pg_db2 = "testdb2"

        run(
            [
                "docker",
                "exec",
                cls.pg_container,
                "sh",
                "-lc",
                (
                    f'psql -U {cls.pg_user} -c "CREATE DATABASE {cls.pg_db1};" || true; '
                    f'psql -U {cls.pg_user} -c "CREATE DATABASE {cls.pg_db2};" || true; '
                ),
            ],
            check=True,
        )

        run(
            [
                "docker",
                "exec",
                cls.pg_container,
                "sh",
                "-lc",
                (
                    f"psql -U {cls.pg_user} -d {cls.pg_db1} -c "
                    '"CREATE TABLE IF NOT EXISTS t (id INT PRIMARY KEY, v TEXT);'
                    "INSERT INTO t(id,v) VALUES (1,'hello-db1') "
                    'ON CONFLICT (id) DO UPDATE SET v=EXCLUDED.v;"'
                ),
            ],
            check=True,
        )
        run(
            [
                "docker",
                "exec",
                cls.pg_container,
                "sh",
                "-lc",
                (
                    f"psql -U {cls.pg_user} -d {cls.pg_db2} -c "
                    '"CREATE TABLE IF NOT EXISTS t (id INT PRIMARY KEY, v TEXT);'
                    "INSERT INTO t(id,v) VALUES (1,'hello-db2') "
                    'ON CONFLICT (id) DO UPDATE SET v=EXCLUDED.v;"'
                ),
            ],
            check=True,
        )

        # --- Seed databases.csv using CLI (star + concrete db) ---
        cls.databases_csv = f"/tmp/{cls.prefix}/databases.csv"

        # IMPORTANT: because we pass --database-containers <container>,
        # get_instance() will use the container name as instance key.
        instance = cls.pg_container

        # Seed star entry (pg_dumpall)
        run(
            [
                "baudolo-seed",
                cls.databases_csv,
                instance,
                "*",
                cls.pg_user,
                cls.pg_password,
            ]
        )

        # Seed concrete DB entry (pg_dump)
        run(
            [
                "baudolo-seed",
                cls.databases_csv,
                instance,
                cls.pg_db1,
                cls.pg_user,
                cls.pg_password,
            ]
        )

        # --- Run baudolo with dump-only-sql ---
        cmd = [
            "baudolo",
            "--compose-dir",
            cls.compose_dir,
            "--databases-csv",
            cls.databases_csv,
            "--database-containers",
            cls.pg_container,
            "--images-no-stop-required",
            "alpine",
            "postgres",
            "mariadb",
            "mysql",
            "--dump-only-sql",
            "--backups-dir",
            cls.backups_dir,
            "--repo-name",
            cls.repo_name,
        ]
        cp = run(cmd, capture=True, check=True)
        cls.stdout = cp.stdout or ""
        cls.stderr = cp.stderr or ""

        cls.hash, cls.version = latest_version_dir(cls.backups_dir, cls.repo_name)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=cls.containers, volumes=cls.volumes)

    def test_db_volume_has_cluster_dump_and_concrete_db_dump_and_no_files(self) -> None:
        base = backup_path(
            self.backups_dir, self.repo_name, self.version, self.db_volume
        )
        sql_dir = base / "sql"
        files_dir = base / "files"

        self.assertTrue(sql_dir.exists(), f"Expected sql dir at: {sql_dir}")
        self.assertFalse(
            files_dir.exists(),
            f"Did not expect files dir for DB volume when dump-only-sql succeeded: {files_dir}",
        )

        # Cluster dump file produced by '*' entry
        cluster = sql_dir / f"{self.pg_container}.cluster.backup.sql"
        self.assertTrue(cluster.is_file(), f"Expected cluster dump file at: {cluster}")

        # Concrete DB dump produced by normal entry
        db1 = sql_dir / f"{self.pg_db1}.backup.sql"
        self.assertTrue(db1.is_file(), f"Expected db dump file at: {db1}")

        # Basic sanity: cluster dump usually contains CREATE DATABASE statements
        txt = cluster.read_text(encoding="utf-8", errors="ignore")
        self.assertIn(
            "CREATE DATABASE",
            txt,
            "Expected cluster dump to contain CREATE DATABASE statements",
        )

    def test_non_db_volume_still_has_files_backup(self) -> None:
        base = backup_path(
            self.backups_dir, self.repo_name, self.version, self.files_volume
        )
        files_dir = base / "files"

        self.assertTrue(
            files_dir.exists(), f"Expected files dir for non-DB volume at: {files_dir}"
        )

        marker = files_dir / "hello.txt"
        self.assertTrue(marker.is_file(), f"Expected marker file at: {marker}")
        self.assertEqual(
            marker.read_text(encoding="utf-8").strip(),
            self.marker,
        )
