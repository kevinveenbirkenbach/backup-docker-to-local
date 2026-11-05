import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from baudolo.restore import run as run_mod
from baudolo.restore.db import cluster as cluster_mod
from baudolo.restore.db import mariadb as mdb_mod
from baudolo.restore.db import postgres as pg_mod
from baudolo.restore.db import version as ver

from .test_version_gate import MARIADB_HEADER, POSTGRES_HEADER, cluster_header

SECRET = "s3cret-Pw"


class TestDockerExecForwardsByName(unittest.TestCase):
    def test_the_value_stays_out_of_the_argv(self):
        with patch.object(run_mod, "run") as run:
            run_mod.docker_exec("db", ["psql"], docker_env={"PGPASSWORD": SECRET})
        cmd = run.call_args.args[0]
        self.assertEqual(
            cmd, ["docker", "exec", "-i", "-e", "PGPASSWORD", "db", "psql"]
        )
        self.assertFalse([arg for arg in cmd if SECRET in arg])
        self.assertEqual(run.call_args.kwargs["env"]["PGPASSWORD"], SECRET)

    def test_the_rest_of_the_environment_is_kept(self):
        with (
            patch.dict(run_mod.os.environ, {"PATH": "/x"}),
            patch.object(run_mod, "run") as run,
        ):
            run_mod.docker_exec("db", ["psql"], docker_env={"PGPASSWORD": SECRET})
        self.assertEqual(run.call_args.kwargs["env"]["PATH"], "/x")

    def test_no_docker_env_inherits_unchanged(self):
        with patch.object(run_mod, "run") as run:
            run_mod.docker_exec("db", ["true"])
        self.assertIsNone(run.call_args.kwargs["env"])
        self.assertEqual(run.call_args.args[0], ["docker", "exec", "-i", "db", "true"])


class TestNoRestoreArgvCarriesThePassword(unittest.TestCase):
    def setUp(self):
        self.argvs = []
        self.envs = []
        self.dir = Path(tempfile.mkdtemp())

        def fake_run(cmd, *, stdin=None, capture=False, env=None):
            self.argvs.append(cmd)
            self.envs.append(env or {})
            stdout = b"17.11\n" if "SHOW server_version" in cmd else b"t1\n"
            if "SELECT VERSION()" in cmd:
                stdout = b"11.8.8-MariaDB\n"
            return MagicMock(stdout=stdout)

        patch.object(run_mod, "run", side_effect=fake_run).start()
        self.addCleanup(patch.stopall)

    def dump(self, name: str, text: str) -> str:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def assert_clean(self, variable: str):
        self.assertTrue(self.argvs)
        for cmd in self.argvs:
            self.assertFalse([arg for arg in cmd if SECRET in arg], cmd)
        self.assertTrue(all(env.get(variable) == SECRET for env in self.envs))

    def test_postgres(self):
        pg_mod.restore_postgres_sql(
            container="db",
            db_name="app",
            user="app",
            password=SECRET,
            sql_path=self.dump("app.backup.sql", POSTGRES_HEADER),
            empty=True,
        )
        self.assert_clean("PGPASSWORD")

    def test_cluster(self):
        with patch.object(cluster_mod, "assert_instance_matches_dump"):
            cluster_mod.restore_cluster_sql(
                container="db",
                user="postgres",
                password=SECRET,
                sql_path=self.dump("c.cluster.backup.sql", cluster_header(roles=1)),
                empty=True,
            )
        self.assert_clean("PGPASSWORD")

    def test_mariadb(self):
        with patch.object(mdb_mod, "_pick_client", return_value="mariadb"):
            mdb_mod.restore_mariadb_sql(
                container="db",
                db_name="app",
                user="app",
                password=SECRET,
                sql_path=self.dump("app.backup.sql", MARIADB_HEADER),
                empty=True,
            )
        self.assert_clean("MYSQL_PWD")
        self.assertEqual(len(self.argvs), 4, "version, list, drop, replay")

    def test_mariadb_version_probe(self):
        ver.server_version("db", "mariadb", "app", SECRET, client="mariadb")
        self.assert_clean("MYSQL_PWD")


if __name__ == "__main__":
    unittest.main()
