"""Running external commands without a shell.

Every command is an argv list. A database name, a password or a container name
therefore cannot close a quote and start a second command, which a formatted
string handed to ``shell=True`` allowed.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class BackupError(Exception):
    """Generic exception for backup errors."""


def _child_env(env: Mapping[str, str] | None) -> dict[str, str] | None:
    return None if env is None else {**os.environ, **env}


def _fail(command: Sequence[str], returncode: int, out: bytes, err: bytes) -> None:
    raise BackupError(
        f"Error in command: {' '.join(command)}\n"
        f"Output: {out}\nError: {err}\n"
        f"Exit code: {returncode}"
    )


def execute_shell_command(
    command: Sequence[str], *, env: Mapping[str, str] | None = None
) -> list[str]:
    """Run *command* and return its stdout lines.

    Args:
        command: argv, the program first.
        env: variables added to the child's environment, for values that must
            not appear in the argv of a process listing.
    """
    command = list(command)
    print(" ".join(command), flush=True)
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_child_env(env)
    )
    out, err = process.communicate()
    if process.returncode != 0:
        _fail(command, process.returncode, out, err)
    return [line.decode("utf-8") for line in out.splitlines()]


def execute_to_file(
    command: Sequence[str], out_file: str, *, env: Mapping[str, str] | None = None
) -> None:
    """Run *command*, writing its stdout to *out_file* only once it succeeded.

    The output goes to a sibling temporary file first, so a partial or empty
    stream from a failing dump never takes the place of a valid backup.
    """
    command = list(command)
    print(" ".join(command), flush=True)
    tmp = Path(f"{out_file}.tmp")
    with tmp.open("wb") as handle:
        process = subprocess.Popen(
            command, stdout=handle, stderr=subprocess.PIPE, env=_child_env(env)
        )
        _, err = process.communicate()
    if process.returncode != 0:
        tmp.unlink()
        _fail(command, process.returncode, b"", err)
    tmp.replace(out_file)
