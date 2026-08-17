"""The databases.csv contract: its columns, its delimiter, and what a row means.

``baudolo-seed`` writes the file, the backup reads it to learn which dumps to
take, and a restore consumer reads it again to replay them. Stating the schema
once keeps a column or a convention added here from being invisible to the
other two.

Field values are handed back exactly as they stand in the file. A password may
legitimately begin or end with a space, so stripping belongs to the caller that
compares, never to the reader.
"""

from __future__ import annotations

import csv
import re
from typing import NamedTuple

COLUMNS = ("instance", "database", "username", "password")
DELIMITER = ";"
CLUSTER_ROW = "*"

_NAME_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_-]*$")


class DatabasesCsvError(ValueError):
    """A row does not match the contract."""


class Row(NamedTuple):
    """One databases.csv row, verbatim.

    ``database`` holds :data:`CLUSTER_ROW` when the whole instance is dumped.
    """

    instance: str
    database: str
    username: str
    password: str

    @property
    def is_cluster(self) -> bool:
        return self.database.strip() == CLUSTER_ROW


def validate_database(value: str | None, *, instance: str) -> str:
    """The database column of one row, or raise.

    The name reaches a shell as part of the dump command, so it is checked
    where it is read as well as where it is written: a file edited by hand
    never passed the seed.

    Args:
        value: the raw column.
        instance: named in the error, so a bad row can be found.

    Raises:
        DatabasesCsvError: the column is empty, literally ``nan``, or holds
            anything but letters, numbers, ``_`` and ``-``.
    """
    text = (value or "").strip()
    if not text:
        raise DatabasesCsvError(
            f"Invalid databases.csv entry for instance '{instance}': column "
            f"'database' must be '{CLUSTER_ROW}' or a concrete database name "
            "(not empty)."
        )
    if text == CLUSTER_ROW:
        return CLUSTER_ROW
    if text.lower() == "nan":
        raise DatabasesCsvError(
            f"Invalid databases.csv entry for instance '{instance}': "
            "database must not be 'nan'."
        )
    if not _NAME_RE.match(text):
        raise DatabasesCsvError(
            f"Invalid databases.csv entry for instance '{instance}': invalid "
            f"database name '{text}'. Allowed: letters, numbers, '_' and '-'."
        )
    return text


def read_rows(csv_path: str) -> list[Row]:
    """Every row of the file in file order, header skipped, blank rows dropped.

    Raises:
        DatabasesCsvError: a row holds fewer columns than :data:`COLUMNS`.
    """
    rows: list[Row] = []
    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter=DELIMITER)
        next(reader, None)
        for raw in reader:
            if not any(field.strip() for field in raw):
                continue
            if len(raw) < len(COLUMNS):
                raise DatabasesCsvError(
                    f"{csv_path} has a row with {len(raw)} column(s), "
                    f"expected {len(COLUMNS)}"
                )
            rows.append(Row(*raw[: len(COLUMNS)]))
    return rows
