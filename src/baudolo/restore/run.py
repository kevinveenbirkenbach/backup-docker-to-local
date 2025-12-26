from __future__ import annotations

import subprocess
import sys
from typing import Optional


def run(
    cmd: list[str],
    *,
    stdin=None,
    capture: bool = False,
    env: Optional[dict] = None,
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

        return subprocess.run(cmd, **kwargs)

    except subprocess.CalledProcessError as e:
        msg = f"ERROR: command failed ({e.returncode}): {' '.join(cmd)}"
        print(msg, file=sys.stderr)
        if e.stdout:
            try:
                print(e.stdout.decode(), file=sys.stderr)
            except Exception:
                print(e.stdout, file=sys.stderr)
        if e.stderr:
            try:
                print(e.stderr.decode(), file=sys.stderr)
            except Exception:
                print(e.stderr, file=sys.stderr)
        raise


def docker_exec(
    container: str,
    argv: list[str],
    *,
    stdin=None,
    capture: bool = False,
    env: Optional[dict] = None,
    docker_env: Optional[dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    cmd: list[str] = ["docker", "exec", "-i"]
    if docker_env:
        for k, v in docker_env.items():
            cmd.extend(["-e", f"{k}={v}"])
    cmd.extend([container, *argv])
    return run(cmd, stdin=stdin, capture=capture, env=env)


def docker_exec_sh(
    container: str,
    script: str,
    *,
    stdin=None,
    capture: bool = False,
    env: Optional[dict] = None,
    docker_env: Optional[dict[str, str]] = None,
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
    )
    return p.returncode == 0
