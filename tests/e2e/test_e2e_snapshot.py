"""Snapshot capture against real filesystems.

Loop devices are only available to a privileged container, so each case builds
its filesystem inside one and drives snapshot_driver.py there. A filesystem
without snapshot support must fail loudly rather than degrade to a live copy,
which is the property that makes the mode safe to offer at all.
"""

from __future__ import annotations

import os
import shutil
import unittest
from pathlib import Path

from .helpers import require_docker, run, unique

REPO_SRC = Path(__file__).resolve().parents[2] / "src"
DRIVER = Path(__file__).resolve().parent / "snapshot_driver.py"
IMAGE = "alpine:3.20"
PACKAGES = "apk add -q btrfs-progs e2fsprogs zfs python3 util-linux"
ATTACH = (
    "LOOP=$(losetup -f | awk '{print $1}') "
    '&& { [ -b "$LOOP" ] || mknod "$LOOP" b 7 "${LOOP#/dev/loop}"; }; '
    'losetup "$LOOP" /img'
)
LOOP_FS = {
    "btrfs": "btrfs subvolume create /subject/docker >/dev/null",
    "ext4": "mkdir -p /subject/docker",
}
# A container carries no /lib/modules, so modprobe fails even on a loaded module.
ZFS_READY = '{ [ -c /dev/zfs ] || modprobe zfs 2>/dev/null; }; [ -c /dev/zfs ]'


def mount_script(fstype: str) -> str:
    """Build a filesystem on a loop device and carve out the snapshot subject."""
    if fstype == "zfs":
        return (
            f"{PACKAGES} && {ZFS_READY} && truncate -s 400M /img "
            "&& zpool create -m none baudolo /img "
            "&& zfs create -o mountpoint=/subject/docker baudolo/docker"
        )
    return (
        f"{PACKAGES} && truncate -s 400M /img && mkfs.{fstype} -q /img "
        f'&& mkdir -p /subject && {ATTACH} && mount -t {fstype} "$LOOP" /subject '
        f"&& {LOOP_FS[fstype]}"
    )


def zfs_usable() -> bool:
    """Whether this host's kernel can serve zfs to a privileged container."""
    proc = run(
        [
            "docker", "run", "--rm", "--privileged", IMAGE, "sh", "-lc",
            f"apk add -q zfs >/dev/null 2>&1 && {ZFS_READY}",
        ],
        capture=True,
        check=False,
    )
    return proc.returncode == 0


def required(fstype: str) -> bool:
    """Whether this run must cover ``fstype`` instead of skipping it.

    CI sets E2E_REQUIRE_FILESYSTEMS so a missing kernel module fails the build
    rather than passing it with a filesystem silently untested.
    """
    demanded = os.environ.get("E2E_REQUIRE_FILESYSTEMS", "")
    return fstype in demanded.replace(",", " ").split()


def stage() -> Path:
    """Copy source and driver under /tmp, the only path the DinD daemon shares."""
    staged = Path("/tmp") / unique("baudolo-e2e-snapshot")
    shutil.copytree(REPO_SRC, staged / "src")
    shutil.copy(DRIVER, staged / "driver.py")
    return staged


def drive(fstype: str, kind: str, expect: str) -> str:
    staged = stage()
    script = (
        f"set -e; {mount_script(fstype)}; "
        f"python3 /driver.py {kind} /subject/docker {expect}"
    )
    try:
        proc = run(
            [
                "docker", "run", "--rm", "--privileged",
                "--name", staged.name,
                "-v", f"{staged / 'src'}:/src:ro",
                "-v", f"{staged / 'driver.py'}:/driver.py:ro",
                IMAGE, "sh", "-lc", script,
            ],
            capture=True,
            check=False,
        )
    finally:
        shutil.rmtree(staged, ignore_errors=True)
    if proc.returncode != 0:
        raise AssertionError(f"{fstype}/{kind} driver failed:\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


class TestE2ESnapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_docker()

    def assert_freezes(self, fstype: str) -> None:
        output = drive(fstype, fstype, "supported")
        self.assertIn("PASS the snapshot exposes the volume", output)
        self.assertIn("PASS a later write does not reach the snapshot", output)
        self.assertIn("PASS the snapshot is removed afterwards", output)
        self.assertIn("ALL OK", output)

    def test_btrfs_snapshot_freezes_the_volume(self) -> None:
        self.assert_freezes("btrfs")

    def test_zfs_snapshot_freezes_the_volume(self) -> None:
        if not zfs_usable():
            if required("zfs"):
                self.fail(
                    "E2E_REQUIRE_FILESYSTEMS demands zfs, but this kernel provides no "
                    "zfs module; load it before running the suite"
                )
            self.skipTest("this kernel provides no zfs module, so no pool can be created")
        self.assert_freezes("zfs")

    def test_ext4_has_no_snapshot_and_says_so(self) -> None:
        output = drive("ext4", "btrfs", "unsupported")
        self.assertIn("PASS refused loudly", output)

    def test_an_unknown_kind_is_refused_before_touching_the_filesystem(self) -> None:
        output = drive("ext4", "lvm", "unsupported")
        self.assertIn("PASS refused loudly", output)


if __name__ == "__main__":
    unittest.main()
