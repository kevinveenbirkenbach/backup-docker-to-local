"""Where a backup run puts its files, and how a finished run is stamped."""

from __future__ import annotations

import json
import pathlib

from dirval import create_stamp_file

from baudolo.generation import MANIFEST_FILE, manifest_document

from .shell import BackupError, execute_shell_command


def get_machine_id() -> str:
    return execute_shell_command(["sha256sum", "/etc/machine-id"])[0][0:64]


def stamp_directory(version_dir: str) -> None:
    """
    Use dirval as a Python library to stamp the directory (no CLI dependency).
    """
    create_stamp_file(version_dir)


def create_version_directory(versions_dir: str, backup_time: str) -> str:
    version_dir = str(pathlib.Path(versions_dir) / backup_time)
    try:
        pathlib.Path(version_dir).mkdir(parents=True)
    except FileExistsError:
        raise BackupError(
            f"generation {backup_time} already exists at {version_dir}; "
            "another run claimed this second - refusing to write into it, "
            "since rsync --delete would overwrite that generation"
        ) from None
    return version_dir


def create_volume_directory(version_dir: str, volume_name: str) -> str:
    path = pathlib.Path(version_dir) / volume_name
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def write_manifest(version_dir: str, volumes: dict[str, dict[str, bool]]) -> str:
    """Record the generation's layout and per-volume outcome.

    Written before the directory is stamped, so the stamp covers it.

    Args:
        version_dir: the generation directory.
        volumes: per volume name, ``database`` and ``dumped``.

    Returns:
        The path written.
    """
    path = pathlib.Path(version_dir) / MANIFEST_FILE
    with path.open("w", encoding="utf-8") as handle:
        json.dump(manifest_document(volumes), handle, indent=2, sort_keys=True)
        handle.write("\n")
    return str(path)
