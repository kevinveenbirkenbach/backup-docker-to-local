"""The on-disk shape of a generation, and the manifest that states it.

Every name a reader needs to find payload in a generation is declared here
once, and written into each generation's own manifest. A consumer therefore
never has to hardcode the layout or match this package's version: it reads
what the run that produced the tree recorded.

The manifest also carries what only the run itself can know: per volume,
``database`` (it held one), ``dumped`` (a dump was produced for it) and
``engine`` (which one was detected). Both flags true is a replayable dump;
``database`` without ``dumped`` is a raw copy of live engine files.

Kept import-free: consumers read the manifest with nothing but ``json``, on
hosts that do not have this package installed.
"""

from __future__ import annotations

FILES_DIR = "files"
SQL_DIR = "sql"
DUMP_SUFFIX = ".backup.sql"
CLUSTER_SUFFIX = ".cluster.backup.sql"

MANIFEST_FILE = "manifest.json"
MANIFEST_SCHEMA = 1


def manifest_document(volumes: dict[str, object]) -> dict[str, object]:
    """The manifest a finished run writes.

    Args:
        volumes: per volume name, an object carrying ``database``, ``dumped``
            and ``engine`` -- a ``baudolo.backup.dumps.VolumeOutcome``.

    Returns:
        The document, ready for ``json.dump``.
    """
    return {
        "schema": MANIFEST_SCHEMA,
        "layout": {
            "files_dir": FILES_DIR,
            "sql_dir": SQL_DIR,
            "dump_suffix": DUMP_SUFFIX,
            "cluster_suffix": CLUSTER_SUFFIX,
        },
        "volumes": {
            name: {
                "database": bool(outcome.database),
                "dumped": bool(outcome.dumped),
                "engine": outcome.engine,
            }
            for name, outcome in sorted(volumes.items())
        },
    }
