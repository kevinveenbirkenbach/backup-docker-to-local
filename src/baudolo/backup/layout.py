"""Where a backup run puts its files, and how a finished run is stamped."""

from __future__ import annotations

import os
import pathlib

from dirval import create_stamp_file

from .shell import execute_shell_command


def get_machine_id() -> str:
    return execute_shell_command("sha256sum /etc/machine-id")[0][0:64]


def stamp_directory(version_dir: str) -> None:
    """
    Use dirval as a Python library to stamp the directory (no CLI dependency).
    """
    create_stamp_file(version_dir)


def create_version_directory(versions_dir: str, backup_time: str) -> str:
    version_dir = os.path.join(versions_dir, backup_time)
    pathlib.Path(version_dir).mkdir(parents=True, exist_ok=True)
    return version_dir


def create_volume_directory(version_dir: str, volume_name: str) -> str:
    path = os.path.join(version_dir, volume_name)
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)
    return path
