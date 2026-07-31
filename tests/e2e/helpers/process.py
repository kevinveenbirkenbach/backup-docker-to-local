"""Process, docker and readiness helpers for the e2e suite."""
from __future__ import annotations

import subprocess
import time
import uuid


def run(
    cmd: list[str],
    *,
    capture: bool = True,
    check: bool = True,
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            check=check,
            cwd=cwd,
            text=True,
            capture_output=capture,
        )
    except subprocess.CalledProcessError as e:
        # Print captured output so failing E2E tests are "live" / debuggable in CI logs
        print(">>> command failed:", " ".join(cmd))
        print(">>> exit code:", e.returncode)
        if e.stdout:
            print(">>> STDOUT:\n" + e.stdout)
        if e.stderr:
            print(">>> STDERR:\n" + e.stderr)
        raise


def sh(
    cmd: str, *, capture: bool = True, check: bool = True
) -> subprocess.CompletedProcess:
    return run(["sh", "-lc", cmd], capture=capture, check=check)


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def require_docker() -> None:
    run(["docker", "version"], capture=True, check=True)


def machine_hash() -> str:
    out = sh("sha256sum /etc/machine-id | awk '{print $1}'").stdout.strip()
    if len(out) < 16:
        raise RuntimeError("Could not determine machine hash from /etc/machine-id")
    return out


def wait_for_log(container: str, pattern: str, timeout_s: int = 60) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        p = run(["docker", "logs", container], capture=True, check=False)
        if pattern in (p.stdout or ""):
            return
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for log pattern '{pattern}' in {container}")


def wait_for_postgres(
    container: str, *, user: str = "postgres", timeout_s: int = 90
) -> None:
    """
    Docker-outside-of-Docker friendly readiness: check from inside the DB container.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        p = run(
            [
                "docker",
                "exec",
                container,
                "sh",
                "-lc",
                f"pg_isready -U {user} -h localhost",
            ],
            capture=True,
            check=False,
        )
        if p.returncode == 0:
            return
        time.sleep(1)
    raise TimeoutError(
        f"Timed out waiting for Postgres readiness in container {container}"
    )


def wait_for_mariadb(
    container: str, *, root_password: str, timeout_s: int = 90
) -> None:
    """
    Liveness probe for MariaDB.

    IMPORTANT (MariaDB 11):
    Root TCP auth is often restricted (unix_socket auth), so a TCP ping like
    `mariadb-admin -uroot -p... -h localhost ping` can fail even though the server is up.
    We therefore check readiness via a socket-based query.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        p = run(
            [
                "docker",
                "exec",
                container,
                "sh",
                "-lc",
                'mariadb -uroot --protocol=socket -e "SELECT 1;"',
            ],
            capture=True,
            check=False,
        )
        if p.returncode == 0:
            return
        time.sleep(1)
    raise TimeoutError(
        f"Timed out waiting for MariaDB readiness in container {container}"
    )


def wait_for_mariadb_sql(
    container: str, *, user: str, password: str, timeout_s: int = 90
) -> None:
    """
    SQL login readiness for the *dedicated test user* over TCP.

    This is separate from wait_for_mariadb(root) because root may be socket-only,
    while the tests use a normal user that should work via TCP.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        p = run(
            [
                "docker",
                "exec",
                container,
                "sh",
                "-lc",
                f'mariadb -h 127.0.0.1 -u{user} -p{password} -e "SELECT 1;"',
            ],
            capture=True,
            check=False,
        )
        if p.returncode == 0:
            return
        time.sleep(1)
    raise TimeoutError(
        f"Timed out waiting for MariaDB SQL login readiness in container {container}"
    )
