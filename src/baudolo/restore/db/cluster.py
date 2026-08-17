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

import os
import re
import tempfile
from collections.abc import Iterable, Iterator

from ..run import docker_exec
from .version import guard

CONTROL_DB = "postgres"
_CLUSTER_PRECLEAN_SQL = os.path.join(os.path.dirname(__file__), "cluster_preclean.sql")
_CREATE_ROLE = re.compile(rb'^CREATE ROLE "?([^";]+)"?;\s*$')


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
    if not os.path.isfile(sql_path):
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
        with open(_CLUSTER_PRECLEAN_SQL, encoding="utf-8") as preclean:
            drop_sql = preclean.read()
        docker_exec(
            container,
            _psql(user),
            stdin=drop_sql.encode(),
            docker_env=docker_env,
        )

    with open(sql_path, "rb") as src, tempfile.TemporaryFile() as filtered:
        for line in filter_own_role_creation(src, user):
            filtered.write(line)
        filtered.seek(0)
        docker_exec(container, _psql(user), stdin=filtered, docker_env=docker_env)

    print(f"PostgreSQL cluster restore complete from '{os.path.basename(sql_path)}'.")
