"""Capture every volume from one atomic filesystem snapshot.

Copying a live tree file by file cannot produce a point in time: a database can
write between two files and leave a control file and its write-ahead log
disagreeing, which no recovery can repair. A snapshot freezes the whole subject
at once, so a database reads it as a crash and replays its log - a case it is
built for. That also removes the reason to stop containers at all.

The snapshot kind is stated by the caller rather than probed, because falling
back to a live copy when a probe is inconclusive would hand out backups that
look consistent and are not.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from .shell import BackupException, execute_shell_command

KINDS = ("btrfs", "zfs")


class SnapshotError(RuntimeError):
    """A snapshot could not be created, resolved or removed."""


def _resolver(subject: str, root: str) -> Callable[[str], str]:
    def resolve(path: str) -> str:
        relative = os.path.relpath(os.path.abspath(path), os.path.abspath(subject))
        if relative.startswith(".."):
            raise SnapshotError(f"{path} lies outside the snapshot subject {subject}")
        resolved = root if relative == "." else os.path.join(root, relative)

        # abspath drops a trailing separator, and rsync reads "dir/" as its
        # contents where "dir" means the directory itself.
        return resolved + os.sep if path.endswith(os.sep) else resolved

    return resolve


def _btrfs(subject: str, name: str, run: Callable[[str], list[str]]) -> tuple[str, str]:
    # The snapshot goes inside the subject, never beside it: the kernel rejects
    # a snapshot whose destination is on another filesystem, which is exactly
    # what the parent directory is when the subject is a mountpoint of its own.
    target = os.path.join(os.path.abspath(subject), f".{name}")
    run(f"btrfs subvolume snapshot -r {subject} {target}")
    return target, f"btrfs subvolume delete {target}"


def _zfs(subject: str, name: str, run: Callable[[str], list[str]]) -> tuple[str, str]:
    output = run(f"zfs list -H -o name {subject}")
    dataset = (output[0] if output else "").strip()
    if not dataset:
        raise SnapshotError(f"no zfs dataset is mounted at {subject}")
    run(f"zfs snapshot {dataset}@{name}")
    root = os.path.join(subject, ".zfs", "snapshot", name)
    return root, f"zfs destroy {dataset}@{name}"


_CREATE = {"btrfs": _btrfs, "zfs": _zfs}


@contextmanager
def volume_snapshot(
    kind: str,
    subject: str,
    tag: str,
    run: Callable[[str], list[str]] = execute_shell_command,
) -> Iterator[Callable[[str], str]]:
    """Yield a resolver mapping a path under ``subject`` into a snapshot of it.

    Args:
        kind: ``btrfs`` or ``zfs``; the caller states it, nothing is probed.
        subject: the btrfs subvolume or zfs dataset mountpoint holding the
            volumes, e.g. ``/var/lib/docker``.
        tag: unique suffix for the snapshot name, e.g. the backup timestamp.
        run: shell runner, injected so the mechanics are testable.

    Raises:
        SnapshotError: the kind is unknown, or the snapshot cannot be created.
            Removal failure is reported, not raised: a leftover snapshot is a
            cleanup problem and must not discard a generation that is complete.
    """
    create = _CREATE.get(kind)
    if create is None:
        raise SnapshotError(f"unknown snapshot kind {kind!r}; expected one of {KINDS}")

    root, remove = create(subject, f"baudolo-{tag}", run)
    try:
        yield _resolver(subject, root)
    finally:
        try:
            run(remove)
        except BackupException as error:
            # Raising here would also mask whatever the body raised.
            print(f"WARNING: {root} could not be removed: {error}", flush=True)
