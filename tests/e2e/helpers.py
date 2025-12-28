# tests/e2e/helpers.py
from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from pathlib import Path


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


def backup_run(
    *,
    backups_dir: str,
    repo_name: str,
    compose_dir: str,
    databases_csv: str,
    database_containers: list[str],
    images_no_stop_required: list[str],
    images_no_backup_required: list[str] | None = None,
    dump_only: bool = False,
) -> None:
    cmd = [
        "baudolo",
        "--compose-dir",
        compose_dir,
        "--docker-compose-hard-restart-required",
        "mailu",
        "--repo-name",
        repo_name,
        "--databases-csv",
        databases_csv,
        "--backups-dir",
        backups_dir,
        "--database-containers",
        *database_containers,
        "--images-no-stop-required",
        *images_no_stop_required,
    ]
    if images_no_backup_required:
        cmd += ["--images-no-backup-required", *images_no_backup_required]
    if dump_only:
        cmd += ["--dump-only"]

    try:
        run(cmd, capture=True, check=True)
    except subprocess.CalledProcessError as e:
        print(">>> baudolo failed (exit code:", e.returncode, ")")
        if e.stdout:
            print(">>> baudolo STDOUT:\n" + e.stdout)
        if e.stderr:
            print(">>> baudolo STDERR:\n" + e.stderr)
        raise


def latest_version_dir(backups_dir: str, repo_name: str) -> tuple[str, str]:
    """
    Returns (hash, version) for the latest backup.
    """
    h = machine_hash()
    root = Path(backups_dir) / h / repo_name
    if not root.is_dir():
        raise FileNotFoundError(str(root))

    versions = sorted([p.name for p in root.iterdir() if p.is_dir()])
    if not versions:
        raise RuntimeError(f"No versions found under {root}")
    return h, versions[-1]


def backup_path(backups_dir: str, repo_name: str, version: str, volume: str) -> Path:
    h = machine_hash()
    return Path(backups_dir) / h / repo_name / version / volume


def create_minimal_compose_dir(base: str) -> str:
    """
    baudolo requires --compose-dir. Create an empty dir with one non-compose subdir.
    """
    p = Path(base) / "compose-root"
    p.mkdir(parents=True, exist_ok=True)
    (p / "noop").mkdir(parents=True, exist_ok=True)
    return str(p)


def write_databases_csv(path: str, rows: list[tuple[str, str, str, str]]) -> None:
    """
    rows: (instance, database, username, password)
    database may be '' (empty) to trigger pg_dumpall behavior if you want, but here we use db name.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("instance;database;username;password\n")
        for inst, db, user, pw in rows:
            f.write(f"{inst};{db};{user};{pw}\n")


def cleanup_docker(*, containers: list[str], volumes: list[str]) -> None:
    for c in containers:
        run(["docker", "rm", "-f", c], capture=True, check=False)
    for v in volumes:
        run(["docker", "volume", "rm", "-f", v], capture=True, check=False)


def ensure_empty_dir(path: str) -> None:
    p = Path(path)
    if p.exists():
        shutil.rmtree(p)
    p.mkdir(parents=True, exist_ok=True)
