from __future__ import annotations

import subprocess


class BackupException(Exception):
    """Generic exception for backup errors."""


def execute_shell_command(command: str) -> list[str]:
    """Execute a shell command and return its output lines."""
    print(command, flush=True)
    process = subprocess.Popen(
        [command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
    )
    out, err = process.communicate()
    if process.returncode != 0:
        raise BackupException(
            f"Error in command: {command}\n"
            f"Output: {out}\nError: {err}\n"
            f"Exit code: {process.returncode}"
        )
    return [line.decode("utf-8") for line in out.splitlines()]
