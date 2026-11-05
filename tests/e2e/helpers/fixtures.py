"""Fixtures and paths the e2e suite builds its scenarios from."""

from __future__ import annotations

import gzip
import shutil
import subprocess
from pathlib import Path

from baudolo.generation import DUMP_SUFFIX, LEGACY_DUMP_SUFFIX
from baudolo.restore.dumpfile import open_dump

from .process import machine_hash, run

# postgres 18+ mounts at /var/lib/postgresql, not /var/lib/postgresql/data.
POSTGRES_IMAGE = "postgres:alpine"
POSTGRES_DATA_DIR = "/var/lib/postgresql"
MARIADB_IMAGE = "mariadb:latest"
MARIADB_DATA_DIR = "/var/lib/mysql"


def backup_run(
    *,
    backups_dir: str,
    repo_name: str,
    compose_dir: str,
    databases_csv: str,
    database_containers: list[str],
    images_no_stop_required: list[str],
    images_no_backup_required: list[str] | None = None,
    only_sql: bool = False,
) -> subprocess.CompletedProcess:
    cmd = [
        "baudolo",
        "--compose-dir",
        compose_dir,
        "--hard-restart-projects",
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
    if only_sql:
        cmd += ["--only-sql"]

    try:
        return run(cmd, capture=True, check=True)
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
    with Path(path).open("w", encoding="utf-8") as f:
        f.write("instance;database;username;password\n")
        f.writelines(f"{inst};{db};{user};{pw}\n" for inst, db, user, pw in rows)


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


def dump_text(path: Path | str) -> str:
    """
    Args:
        path: a dump, gzip-compressed or plain.

    Returns:
        Its SQL text.
    """
    with open_dump(str(path)) as handle:
        return handle.read().decode("utf-8", errors="replace")


def write_dump_text(path: Path | str, text: str) -> None:
    """
    Args:
        path: a gzip dump to overwrite.
        text: the SQL text it carries afterwards.
    """
    with gzip.open(str(path), "wb") as handle:
        handle.write(text.encode("utf-8"))


def dumps_in(sql_dir: Path) -> list[Path]:
    """
    Args:
        sql_dir: a volume's sql directory, which may be absent.

    Returns:
        Every dump in it, compressed or plain, single-database or cluster.
    """
    if not sql_dir.is_dir():
        return []
    return sorted(
        {*sql_dir.glob(f"*{DUMP_SUFFIX}"), *sql_dir.glob(f"*{LEGACY_DUMP_SUFFIX}")}
    )


def assert_dumps_in_sees_both_suffixes(case, scratch: str) -> None:
    """
    Args:
        case: the running ``unittest.TestCase``.
        scratch: an empty directory to place the probe dumps in.
    """
    probe = Path(scratch) / "dumps-in-probe"
    probe.mkdir(parents=True, exist_ok=True)
    expected = [probe / f"a{DUMP_SUFFIX}", probe / f"b{LEGACY_DUMP_SUFFIX}"]
    for path in expected:
        path.write_bytes(b"")
    case.assertEqual(dumps_in(probe), expected)
