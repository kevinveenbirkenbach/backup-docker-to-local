import unittest
from unittest.mock import patch

from baudolo.backup import docker as docker_mod


def _with_image(reference: str):
    return patch.object(docker_mod, "execute_shell_command", return_value=[reference])


class TestImageName(unittest.TestCase):
    def test_plain_reference(self) -> None:
        with _with_image("postgres:16"):
            self.assertEqual(docker_mod.image_name("c1"), "postgres")

    def test_registry_host_is_dropped(self) -> None:
        with _with_image("svc-db-mariadb-swarm-mgr-01:5000/postgres_custom:17-3.5"):
            self.assertEqual(docker_mod.image_name("c1"), "postgres_custom")

    def test_pull_through_path_is_kept(self) -> None:
        with _with_image(
            "svc-db-mariadb-swarm-mgr-01:5000/ghcr.io/x/mirror/docker.io/postgres:16"
        ):
            self.assertEqual(
                docker_mod.image_name("c1"), "ghcr.io/x/mirror/docker.io/postgres"
            )

    def test_digest_is_dropped(self) -> None:
        with _with_image("registry:5000/postgres@sha256:" + "0" * 64):
            self.assertEqual(docker_mod.image_name("c1"), "postgres")


class TestHasImage(unittest.TestCase):
    def test_registry_hostname_does_not_decide_the_engine(self) -> None:
        with _with_image("svc-db-mariadb-swarm-mgr-01:5000/postgres_custom:17-3.5"):
            self.assertFalse(docker_mod.has_image("c1", "mariadb"))
        with _with_image("svc-db-mariadb-swarm-mgr-01:5000/postgres_custom:17-3.5"):
            self.assertTrue(docker_mod.has_image("c1", "postgres"))

    def test_tag_does_not_decide_the_engine(self) -> None:
        with _with_image("registry:5000/xwiki_custom:lts-postgres-tomcat"):
            self.assertFalse(docker_mod.has_image("c1", "postgres"))

    def test_mirrored_mariadb_still_matches(self) -> None:
        with _with_image("registry:5000/ghcr.io/x/mirror/docker.io/mariadb:11"):
            self.assertTrue(docker_mod.has_image("c1", "mariadb"))


if __name__ == "__main__":
    unittest.main()
