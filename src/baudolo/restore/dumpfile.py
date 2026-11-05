from __future__ import annotations

import gzip
from pathlib import Path
from typing import BinaryIO

from baudolo.generation import COMPRESSED_SUFFIX

GZIP_MAGIC = b"\x1f\x8b"
VERIFY_BYTES = 1 << 20


def is_gzip(path: str) -> bool:
    """
    Args:
        path: a dump file.

    Returns:
        True when its first bytes are the gzip magic, whatever its name says.
    """
    with Path(path).open("rb") as handle:
        return handle.read(len(GZIP_MAGIC)) == GZIP_MAGIC


def open_dump(path: str) -> BinaryIO:
    """
    Args:
        path: a dump, gzip-compressed or plain.

    Returns:
        A binary reader yielding the SQL text either way.
    """
    if is_gzip(path):
        return gzip.open(path, "rb")
    return Path(path).open("rb")


def verify(path: str) -> None:
    """
    Args:
        path: a dump; a gzip one is decompressed to its end, a plain one is
            left alone.

    Raises:
        EOFError: the gzip stream is truncated.
        gzip.BadGzipFile: its header, CRC or length is wrong.
        zlib.error: its deflate data is corrupt.
    """
    if not is_gzip(path):
        return
    with gzip.open(path, "rb") as handle:
        while handle.read(VERIFY_BYTES):
            pass


def locate(path: str) -> str:
    """
    Args:
        path: where this version writes the dump, ending in COMPRESSED_SUFFIX.

    Returns:
        *path*, or the uncompressed name earlier versions wrote, whichever
        exists.

    Raises:
        FileNotFoundError: neither exists.
        FileExistsError: both exist.
    """
    legacy = path.removesuffix(COMPRESSED_SUFFIX)
    found = [
        candidate
        for candidate in dict.fromkeys((path, legacy))
        if Path(candidate).is_file()
    ]
    if len(found) > 1:
        raise FileExistsError(
            f"both {path} and {legacy} exist; remove the one that must not be replayed"
        )
    if not found:
        raise FileNotFoundError(f"neither {path} nor {legacy} exists")
    return found[0]
