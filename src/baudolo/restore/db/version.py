"""Refuse a dump the target engine is too old to read.

A restore with ``--empty`` destroys before it replays: the pre-clean drops the
schema in one session and the dump goes in the next, with no rollback across
the two. A dump the engine cannot parse therefore does not fail harmlessly -
it leaves an emptied database behind. Comparing the two versions first turns
that into a refusal.

Both engines state their origin in the dump's own header, and they do not
state it the same way. Postgres writes ``-- Dumped from database version``
around line seven. MariaDB opens line two with ``-- MariaDB dump 10.19-11.8.8``,
where the first number is mariadb-dump's own version, and names the server only
further down on the tab-separated ``-- Server version`` line. Matching the first
number in the header would read the tool on one engine and the server on the
other, so each engine gets its own pattern.

A ``pg_dumpall`` cluster dump has no version line of its own: its header opens
with the cluster banner and the roles section, and the first
``-- Dumped from database version`` belongs to the first database's embedded
``pg_dump`` output, arbitrarily far down. Hence the scan runs to
``SCAN_LINES`` rather than to a header-sized handful.
"""

from __future__ import annotations

import re

from ..run import docker_exec, stdout_of

SCAN_LINES = 2000
DUMP_VERSION = {
    "postgres": re.compile(r"^-- Dumped from database version (\S+)"),
    "mariadb": re.compile(r"^-- Server version\s+(\S+)"),
}


class VersionMismatch(Exception):
    """The dump cannot be replayed into this engine."""


def major_of(version: str) -> int:
    """The major number of an engine version string.

    Args:
        version: as the engine spells it, e.g. ``17.11`` or
            ``11.8.8-MariaDB-ubu2404``.

    Raises:
        VersionMismatch: the string does not start with a number.
    """
    leading = re.match(r"(\d+)", version)
    if not leading:
        raise VersionMismatch(f"cannot read a major version from '{version}'")
    return int(leading.group(1))


def dump_version(sql_path: str, engine: str) -> str:
    """Read the engine version a dump was taken from, out of its own header.

    Args:
        sql_path: the dump to read.
        engine: ``postgres`` or ``mariadb``.

    Returns:
        The version string as the dump spells it.

    Raises:
        VersionMismatch: no version line within the first ``SCAN_LINES``.
    """
    pattern = DUMP_VERSION[engine]
    with open(sql_path, encoding="utf-8", errors="replace") as handle:
        for _ in range(SCAN_LINES):
            line = handle.readline()
            if not line:
                break
            found = pattern.search(line)
            if found:
                return found.group(1)
    raise VersionMismatch(
        f"{sql_path} carries no {engine} version header in its first {SCAN_LINES} lines"
    )


def server_version(
    container: str, engine: str, user: str, password: str, client: str = ""
) -> str:
    """Ask the running engine which version it is."""
    if engine == "postgres":
        return stdout_of(
            docker_exec(
                container,
                ["psql", "-U", user, "-tAc", "SHOW server_version"],
                capture=True,
                docker_env={"PGPASSWORD": password},
            )
        )
    return stdout_of(
        docker_exec(
            container,
            [
                client or "mariadb",
                "-u",
                user,
                f"--password={password}",
                "-N",
                "-B",
                "-e",
                "SELECT VERSION()",
            ],
            capture=True,
        )
    )


def assert_replayable(sql_path: str, engine: str, dumped: str, serving: str) -> None:
    """Refuse a dump from a newer major version than the target engine.

    Restoring forward across a major version is the upgrade path and stays
    allowed; backward is refused, because a newer dump uses syntax an older
    server rejects and the pre-clean would already have dropped the schema.

    Raises:
        VersionMismatch: the dump is newer than the engine.
    """
    if major_of(dumped) > major_of(serving):
        raise VersionMismatch(
            f"{sql_path} came from {engine} {dumped} but {serving} is running; "
            "a newer dump does not replay into an older engine, and --empty "
            "would drop the schema before finding out"
        )


def guard(
    *,
    sql_path: str,
    engine: str,
    container: str,
    user: str,
    password: str,
    client: str = "",
) -> None:
    """Compare the dump's origin against the running engine before replaying."""
    dumped = dump_version(sql_path, engine)
    serving = server_version(container, engine, user, password, client)
    assert_replayable(sql_path, engine, dumped, serving)
    print(f"OK: dump is from {engine} {dumped}, {serving} is serving.")
