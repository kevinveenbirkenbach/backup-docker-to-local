from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
from typing import BinaryIO

STREAM_BYTES = 1 << 20


def run(
    cmd: list[str],
    *,
    stdin=None,
    capture: bool = False,
    env: dict | None = None,
) -> subprocess.CompletedProcess:
    try:
        kwargs: dict = {
            "check": True,
            "capture_output": capture,
            "env": env,
        }

        # If stdin is raw data (bytes/str), pass it via input=.
        # IMPORTANT: when using input=..., do NOT pass stdin=... as well.
        if isinstance(stdin, (bytes, str)):
            kwargs["input"] = stdin
        else:
            kwargs["stdin"] = stdin

        return subprocess.run(cmd, **kwargs)  # noqa: PLW1510 - check lives in kwargs

    except subprocess.CalledProcessError as e:
        msg = f"ERROR: command failed ({e.returncode}): {' '.join(cmd)}"
        print(msg, file=sys.stderr)
        for stream in (e.stdout, e.stderr):
            if not stream:
                continue
            try:
                print(stream.decode(), file=sys.stderr)
            except (UnicodeDecodeError, AttributeError):
                print(stream, file=sys.stderr)
        raise


def stdout_of(completed: subprocess.CompletedProcess) -> str:
    """The captured stdout as stripped text, whether it came back bytes or str."""
    raw = completed.stdout or b""
    return (raw.decode() if isinstance(raw, bytes) else raw).strip()


def docker_exec_cmd(
    container: str, argv: list[str], docker_env: dict[str, str] | None
) -> list[str]:
    """
    Args:
        container: the container to run in.
        argv: the command, already split.
        docker_env: variables to hand to the container; only their names
            reach the returned argv.

    Returns:
        The ``docker exec -i`` argv.
    """
    forwarded = [arg for name in docker_env or {} for arg in ("-e", name)]
    return ["docker", "exec", "-i", *forwarded, container, *argv]


def child_env(env: dict | None, docker_env: dict[str, str] | None) -> dict | None:
    """
    Args:
        env: the docker CLI's environment, or None to inherit this process's.
        docker_env: variables whose values the docker CLI copies into the
            container for a bare ``-e NAME``.

    Returns:
        The environment for the docker CLI, or None to inherit unchanged.
    """
    if not docker_env:
        return env
    return {**(os.environ if env is None else env), **docker_env}


def docker_exec(
    container: str,
    argv: list[str],
    *,
    stdin=None,
    capture: bool = False,
    env: dict | None = None,
    docker_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    return run(
        docker_exec_cmd(container, argv, docker_env),
        stdin=stdin,
        capture=capture,
        env=child_env(env, docker_env),
    )


def docker_exec_stream(
    container: str,
    argv: list[str],
    *,
    source: BinaryIO,
    docker_env: dict[str, str] | None = None,
) -> None:
    """
    Args:
        container: the container to run in.
        argv: the command, fed *source* on stdin.
        source: a binary reader, copied in STREAM_BYTES chunks, so a reader
            without a file descriptor of its own, such as a gzip one, works.
        docker_env: as for :func:`docker_exec`.

    Raises:
        subprocess.CalledProcessError: the command exited non-zero.
    """
    cmd = docker_exec_cmd(container, argv, docker_env)
    process = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, env=child_env(None, docker_env)
    )
    try:
        with contextlib.suppress(BrokenPipeError):
            shutil.copyfileobj(source, process.stdin, STREAM_BYTES)
        with contextlib.suppress(BrokenPipeError):
            process.stdin.close()
    except BaseException:
        process.kill()
        process.wait()
        raise
    returncode = process.wait()
    if returncode != 0:
        print(f"ERROR: command failed ({returncode}): {' '.join(cmd)}", file=sys.stderr)
        raise subprocess.CalledProcessError(returncode, cmd)


def docker_exec_sh(
    container: str,
    script: str,
    *,
    stdin=None,
    capture: bool = False,
    env: dict | None = None,
    docker_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    return docker_exec(
        container,
        ["sh", "-lc", script],
        stdin=stdin,
        capture=capture,
        env=env,
        docker_env=docker_env,
    )


def docker_volume_exists(volume: str) -> bool:
    p = subprocess.run(
        ["docker", "volume", "inspect", volume],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return p.returncode == 0
