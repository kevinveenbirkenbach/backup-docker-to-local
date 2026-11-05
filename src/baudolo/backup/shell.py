"""Running external commands without a shell.

Every command is an argv list. A database name, a password or a container name
therefore cannot close a quote and start a second command, which a formatted
string handed to ``shell=True`` allowed.
"""

from __future__ import annotations

import gzip
import os
import subprocess
import tempfile
import zlib
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

GZIP_LEVEL = 6
READ_BYTES = 1 << 20
SYNC_BYTES = 1 << 16


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


def is_sync_point(piece: bytes) -> bool:
    """
    Args:
        piece: a line of the dump, or a READ_BYTES slice of a longer one.

    Returns:
        True when a full flush follows *piece*, decided by its bytes alone, on
        average once per SYNC_BYTES of input.
    """
    return zlib.crc32(piece) % max(1, SYNC_BYTES // len(piece)) == 0


def _abort(process: subprocess.Popen, tmp: Path) -> None:
    process.kill()
    process.wait()
    tmp.unlink(missing_ok=True)


def execute_to_gzip(
    command: Sequence[str], out_file: str, *, env: Mapping[str, str] | None = None
) -> None:
    """
    Args:
        command: argv, the program first; its stdout is the dump.
        out_file: the final gzip path. The stream is written to
            ``<out_file>.tmp`` and renamed only after the command exited 0.
        env: variables added to the child's environment.

    Raises:
        BackupError: the command failed, or the file could not be written.
    """
    command = list(command)
    print(" ".join(command), flush=True)
    tmp = Path(f"{out_file}.tmp")
    with tempfile.TemporaryFile() as err_sink:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=err_sink, env=_child_env(env)
        )
        try:
            with (
                tmp.open("wb") as raw,
                gzip.GzipFile(
                    filename="",
                    mode="wb",
                    fileobj=raw,
                    compresslevel=GZIP_LEVEL,
                    mtime=0,
                ) as packed,
            ):
                for piece in iter(partial(process.stdout.readline, READ_BYTES), b""):
                    packed.write(piece)
                    if is_sync_point(piece):
                        packed.flush(zlib.Z_FULL_FLUSH)
        except OSError as error:
            _abort(process, tmp)
            raise BackupError(f"Error writing {out_file}: {error}") from error
        except BaseException:
            _abort(process, tmp)
            raise
        finally:
            process.stdout.close()
        returncode = process.wait()
        err_sink.seek(0)
        err = err_sink.read()
    if returncode != 0:
        tmp.unlink()
        _fail(command, returncode, b"", err)
    tmp.replace(out_file)
