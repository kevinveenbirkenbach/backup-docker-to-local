"""Capture every volume from one atomic filesystem snapshot.

Copying a live tree file by file cannot produce a point in time: a database can
write between two files and leave a control file and its write-ahead log
disagreeing, which no recovery can repair. A snapshot freezes the whole subject
at once, so a database reads it as a crash and replays its log - a case it is
built for. That also removes the reason to stop containers at all.

The snapshot kind is stated by the caller rather than probed, because falling
back to a live copy when a probe is inconclusive would hand out backups that
look consistent and are not.

Which volumes a snapshot of the subject contains is a different question, and
it is decided per volume: a volume with a backing store of its own appears
inside the snapshot as an existing empty directory, so copying from there
succeeds and stores nothing. Such a volume is copied live instead - correct
data without the point in time - while every other volume of the same run
keeps its snapshot.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from .shell import BackupError, execute_shell_command

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from .volume import Backing

KINDS = ("btrfs", "zfs")


class SnapshotError(RuntimeError):
    """A snapshot could not be created, resolved or removed."""


def _resolver(subject: str, root: str) -> Callable[[str], str]:
    def resolve(path: str) -> str:
        # Exception: abspath, not Path.resolve() - resolve() follows symlinks,
        # which would let a symlinked volume test as inside the subject.
        relative = os.path.relpath(
            os.path.abspath(path),  # noqa: PTH100
            os.path.abspath(subject),  # noqa: PTH100
        )
        if relative.startswith(".."):
            raise SnapshotError(f"{path} lies outside the snapshot subject {subject}")
        resolved = root if relative == "." else str(Path(root) / relative)

        # abspath drops a trailing separator, and rsync reads "dir/" as its
        # contents where "dir" means the directory itself.
        return resolved + os.sep if path.endswith(os.sep) else resolved

    return resolve


def _btrfs(
    subject: str, name: str, run: Callable[[list[str]], list[str]]
) -> tuple[str, list[str]]:
    # The snapshot goes inside the subject, never beside it: the kernel rejects
    # a snapshot whose destination is on another filesystem, which is exactly
    # what the parent directory is when the subject is a mountpoint of its own.
    target = str(Path(os.path.abspath(subject)) / f".{name}")  # noqa: PTH100 - see _resolver
    run(["btrfs", "subvolume", "snapshot", "-r", subject, target])
    return target, ["btrfs", "subvolume", "delete", target]


def _zfs(
    subject: str, name: str, run: Callable[[list[str]], list[str]]
) -> tuple[str, list[str]]:
    output = run(["zfs", "list", "-H", "-o", "name", subject])
    dataset = (output[0] if output else "").strip()
    if not dataset:
        raise SnapshotError(f"no zfs dataset is mounted at {subject}")
    run(["zfs", "snapshot", f"{dataset}@{name}"])
    root = str(Path(subject) / ".zfs" / "snapshot" / name)
    return root, ["zfs", "destroy", f"{dataset}@{name}"]


_CREATE = {"btrfs": _btrfs, "zfs": _zfs}


def unsnapshotted(backing: Backing, subject: str) -> str | None:
    """Return why a snapshot of ``subject`` does not hold this volume's data.

    Docker mounts a volume's own backing store lazily and unmounts it when the
    last consumer stops, so the declaration is what gets checked: it is true at
    every moment, where the mount table is only true while a container happens
    to hold the volume.

    Args:
        backing: the volume as the daemon describes it.
        subject: the snapshot subject, e.g. ``/var/lib/docker``.

    Returns:
        The reason, or None when the snapshot holds the volume.
    """
    if backing.driver != "local":
        return f"it uses the {backing.driver} driver"
    if backing.options:
        return f"it declares its own backing store {backing.options}"
    if not backing.mountpoint:
        return "it reports no mountpoint"
    real = os.path.realpath(backing.mountpoint)
    if os.path.ismount(real):
        return f"its mountpoint {backing.mountpoint} sits on its own mount"
    try:
        crosses = (
            Path(real).stat().st_dev != Path(os.path.realpath(subject)).stat().st_dev
        )
    except OSError as error:
        return f"its mountpoint {backing.mountpoint} could not be read: {error}"
    if crosses:
        return f"its mountpoint {backing.mountpoint} crosses a filesystem boundary"
    return None


def snapshot_source(
    resolve: Callable[[str], str], backing: Backing, subject: str
) -> tuple[str | None, str]:
    """Resolve where to read a volume from, and why if not from the snapshot.

    Returns:
        ``(path, "")`` to copy from the snapshot, or ``(None, reason)`` to copy
        it live.
    """
    reason = unsnapshotted(backing, subject)
    if reason:
        return None, reason
    try:
        source = resolve(backing.source)
    except SnapshotError as error:
        return None, str(error)
    if not Path(source).is_dir():
        return None, "it was created after the snapshot was taken"
    return source, ""


@contextmanager
def volume_snapshot(
    kind: str,
    subject: str,
    tag: str,
    run: Callable[[list[str]], list[str]] = execute_shell_command,
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
        except BackupError as error:
            # Raising here would also mask whatever the body raised.
            print(f"WARNING: {root} could not be removed: {error}", flush=True)
