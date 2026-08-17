"""Restoring files into a volume that has a backing store of its own.

Docker keeps the same ``/var/lib/docker/volumes/<name>/_data`` path for such a
volume and mounts the real storage over it only while a container holds it.
Writing there unmounted lands in the empty directory underneath, is hidden by
the next mount, and rsync reports success - so the restore has to refuse.
"""

import unittest
from pathlib import Path

from .helpers import (
    backup_path,
    cleanup_docker,
    ensure_empty_dir,
    machine_hash,
    require_docker,
    run,
    unique,
)

MARKER = "restored-payload"
VERSION = "20260817000000"


def mountpoint_of(volume: str) -> Path:
    return Path("/var/lib/docker/volumes") / volume / "_data"


def contents(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir()) if directory.is_dir() else []


class TestE2ERestoreFilesBackingStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()
        cls.prefix = unique("baudolo-e2e-backing")
        cls.repo_name = cls.prefix
        cls.backups_dir = f"/tmp/{cls.prefix}/Backups"
        cls.backing = Path(f"/tmp/{cls.prefix}/backing")
        ensure_empty_dir(cls.backups_dir)
        ensure_empty_dir(str(cls.backing))

        cls.bound_volume = f"{cls.prefix}-bound"
        cls.plain_volume = f"{cls.prefix}-plain"
        cls.volumes = [cls.bound_volume, cls.plain_volume]

        for volume in cls.volumes:
            files = (
                backup_path(cls.backups_dir, cls.repo_name, VERSION, volume) / "files"
            )
            files.mkdir(parents=True, exist_ok=True)
            (files / "marker.txt").write_text(MARKER, encoding="utf-8")

        run(
            [
                "docker",
                "volume",
                "create",
                "--driver",
                "local",
                "--opt",
                "type=none",
                "--opt",
                "o=bind",
                "--opt",
                f"device={cls.backing}",
                cls.bound_volume,
            ]
        )
        run(["docker", "volume", "create", cls.plain_volume])

        cls.refused = cls.restore(cls.bound_volume)
        cls.accepted = cls.restore(cls.plain_volume)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_docker(containers=[], volumes=cls.volumes)

    @classmethod
    def restore(cls, volume: str):
        return run(
            [
                "baudolo-restore",
                "files",
                volume,
                machine_hash(),
                VERSION,
                "--backups-dir",
                cls.backups_dir,
                "--repo-name",
                cls.repo_name,
            ],
            check=False,
        )

    def test_a_volume_with_its_own_backing_store_is_refused(self) -> None:
        self.assertEqual(self.refused.returncode, 2, self.refused.stdout)
        self.assertIn("backing store of its own", self.refused.stderr)

    def test_nothing_was_written_into_the_backing_store(self) -> None:
        self.assertEqual(contents(self.backing), [])

    def test_nothing_was_written_under_the_mount_either(self) -> None:
        self.assertEqual(
            contents(mountpoint_of(self.bound_volume)),
            [],
            "the copy landed in the directory the next mount hides",
        )

    def test_a_plain_volume_is_still_restored(self) -> None:
        self.assertEqual(self.accepted.returncode, 0, self.accepted.stderr)
        restored = mountpoint_of(self.plain_volume) / "marker.txt"
        self.assertTrue(restored.is_file(), f"{restored} missing")
        self.assertEqual(restored.read_text(encoding="utf-8"), MARKER)


if __name__ == "__main__":
    unittest.main()
