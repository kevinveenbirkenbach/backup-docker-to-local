"""Replay a full PostgreSQL cluster dump produced by ``pg_dumpall``.

The backup side writes one when a databases.csv row asks for every database of
an instance (``database = '*'``, see ``backup/db.py``). Until now nothing read
it back, so that dump was stored and unrestorable - a format whose producer has
no consumer.

A cluster stream differs from a single-database one in three ways that decide
the implementation:

* it recreates roles and databases, so it must be replayed against the control
  database rather than into a target database;
* ``CREATE DATABASE`` cannot run inside a transaction block, so unlike
  :mod:`baudolo.restore.db.postgres` the replay must not be wrapped in
  ``--single-transaction``;
* it is replayed as a superuser, so the superuser-only statements that the
  single-database path filters out are exactly the ones that have to survive.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from baudolo.restore.run import docker_exec

from .version import guard

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

CONTROL_DB = "postgres"
_CLUSTER_PRECLEAN_SQL = Path(__file__).parent / "cluster_preclean.sql"
_CREATE_ROLE = re.compile(rb'^CREATE ROLE "?([^";]+)"?;\s*$')
_CREATE_DATABASE = re.compile(rb"^CREATE DATABASE\s+(.*)$")
_CREATE_ROLE_LINE = re.compile(rb"^CREATE ROLE\s+(.*)$")
_CONNECT = re.compile(rb"^\\connect\s+(.*)$")
_NO_ROWS = "SELECT ''::text WHERE false"


def _first_identifier(rest: str) -> str | None:
    """The first SQL identifier in *rest*, quoted or bare.

    A quoted identifier may hold spaces and doubled quotes, so it cannot be
    read with a character class that stops at whitespace - which is how a
    database called ``odd name`` used to leave the inventory as ``odd``.
    """
    text = rest.strip()
    if not text:
        return None
    if text.startswith('"'):
        out = []
        index = 1
        while index < len(text):
            char = text[index]
            if char == '"':
                if index + 1 < len(text) and text[index + 1] == '"':
                    out.append('"')
                    index += 2
                    continue
                return "".join(out)
            out.append(char)
            index += 1
        return None
    return re.split(r"[\s;(]", text, maxsplit=1)[0] or None


def _connect_target(rest: str) -> str | None:
    """The database a ``\\connect`` line switches to.

    psql options precede the name (``\\connect -reuse-previous=on dbname=x``),
    and the name may arrive as a ``dbname=`` assignment rather than bare.
    """
    for token in rest.strip().split():
        if token.startswith("-"):
            continue
        if token.startswith("dbname="):
            return _first_identifier(token[len("dbname=") :])
        return _first_identifier(rest.strip()[rest.strip().index(token) :])
    return None


def dump_inventory(sql_path: str) -> tuple[list[str], list[str]]:
    """The databases and roles a cluster dump recreates.

    Args:
        sql_path: the ``pg_dumpall`` stream.

    Returns:
        ``(databases, roles)``, each in the order the dump names them. The
        pre-clean is scoped to these: everything else in the instance belongs
        to no backup this restore holds, and dropping it would destroy data
        the replay cannot bring back.
    """
    databases: list[str] = []
    roles: list[str] = []
    with Path(sql_path).open("rb") as handle:
        for raw in handle:
            line = raw.decode("utf-8", "replace")
            for pattern, sink, read in (
                (_CREATE_DATABASE, databases, _first_identifier),
                (_CONNECT, databases, _connect_target),
                (_CREATE_ROLE_LINE, roles, _first_identifier),
            ):
                found = pattern.match(raw)
                if not found:
                    continue
                name = read(line[found.start(1) :])
                if name and name not in sink:
                    sink.append(name)
    return databases, roles


def preclean_sql() -> str:
    """The catalog-wide pre-clean, safe only behind the instance check."""
    with _CLUSTER_PRECLEAN_SQL.open(encoding="utf-8") as preclean:
        return preclean.read()


def instance_databases(container: str, user: str, docker_env: dict) -> list[str]:
    """The instance's own databases, templates and control database aside."""
    listed = docker_exec(
        container,
        [
            "psql",
            "-U",
            user,
            "-d",
            CONTROL_DB,
            "-tAc",
            (
                "SELECT datname FROM pg_database "
                "WHERE NOT datistemplate AND datname <> current_database()"
            ),
        ],
        capture=True,
        docker_env=docker_env,
    ).stdout
    text = listed.decode() if isinstance(listed, bytes) else listed
    return [name for name in text.split() if name]


def assert_instance_matches_dump(
    container: str, user: str, sql_path: str, docker_env: dict
) -> None:
    """Refuse ``--empty`` on an instance holding anything the dump lacks.

    The pre-clean is a catalog-wide sweep, so a foreign database would be
    destroyed with no way back. Scoping the sweep instead is not a fix: a
    surviving database that owns or grants to one of the dump's roles pins
    that role in pg_shdepend, and DROP ROLE then fails after the dump's own
    databases are already gone.

    Raises:
        RuntimeError: the instance carries databases this dump cannot restore.
    """
    dumped, _roles = dump_inventory(sql_path)
    present = instance_databases(container, user, docker_env)
    foreign = sorted(set(present) - set(dumped))
    if foreign:
        raise RuntimeError(
            f"{container} also holds {', '.join(foreign)}, which "
            f"{Path(sql_path).name} does not carry. --empty wipes the "
            "instance, so those would be destroyed with nothing to restore "
            "them from. Move them off this instance, or drop them yourself if "
            "they are disposable."
        )


def _psql(user: str) -> list[str]:
    """The replay client: no --single-transaction, CREATE DATABASE forbids it."""
    return ["psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", CONTROL_DB]


def filter_own_role_creation(lines: Iterable[bytes], user: str) -> Iterator[bytes]:
    """Drop the ``CREATE ROLE`` of the role holding this session.

    A pg_dumpall stream recreates every role of the cluster, the bootstrap
    superuser included, and the pre-clean cannot drop the one it is connected
    as - so that single statement always collides. Its ``ALTER ROLE`` is kept:
    that is what re-applies the attributes and the password the dump captured.

    Args:
        lines: dump lines including their trailing newlines.
        user: the connecting role.

    Yields:
        Every line except that one CREATE.
    """
    for line in lines:
        found = _CREATE_ROLE.match(line)
        if found and found.group(1).decode() == user:
            continue
        yield line


def restore_cluster_sql(
    *,
    container: str,
    user: str,
    password: str,
    sql_path: str,
    empty: bool,
    check_version: bool = True,
) -> None:
    """Replay a pg_dumpall stream into a running instance.

    Args:
        container: the running engine to replay into.
        user: a superuser of that instance; the dump creates roles and
            databases, which an application role may not do.
        password: its password, handed to psql through the container's env.
        sql_path: the ``<instance>.cluster.backup.sql`` of a generation.
        empty: drop the cluster's databases and roles first. Without it the
            replay stops at the first object that already exists, which is the
            honest outcome: recreating a cluster over a populated one is a
            decision, not a default.
        check_version: refuse a dump from a newer major version than the
            running engine before anything is dropped.
    """
    if not Path(sql_path).is_file():
        raise FileNotFoundError(sql_path)

    if check_version:
        guard(
            sql_path=sql_path,
            engine="postgres",
            container=container,
            user=user,
            password=password,
        )

    docker_env = {"PGPASSWORD": password}

    if empty:
        assert_instance_matches_dump(container, user, sql_path, docker_env)
        docker_exec(
            container,
            _psql(user),
            stdin=preclean_sql().encode(),
            docker_env=docker_env,
        )

    with Path(sql_path).open("rb") as src, tempfile.TemporaryFile() as filtered:
        for line in filter_own_role_creation(src, user):
            filtered.write(line)
        filtered.seek(0)
        docker_exec(container, _psql(user), stdin=filtered, docker_env=docker_env)

    print(f"PostgreSQL cluster restore complete from '{Path(sql_path).name}'.")
