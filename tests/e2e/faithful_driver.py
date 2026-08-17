"""Show what a real snapshot holds for a volume that has its own storage.

Runs inside the privileged container that built the btrfs subject. Prints one
PASS/FAIL line per assertion and exits non-zero on the first failure.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/src")

from baudolo.backup.snapshot import (
    SnapshotError,
    snapshot_source,
    unsnapshotted,
    volume_snapshot,
)
from baudolo.backup.volume import Backing

SUBJECT = sys.argv[1]


def shell(command: str) -> list[str]:
    proc = subprocess.run(
        command, shell=True, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise SnapshotError(
            f"{command} exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return proc.stdout.splitlines()


def check(label: str, condition: bool) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}", flush=True)
    if not condition:
        sys.exit(1)


def volume(name: str, payload: str) -> Path:
    path = Path(SUBJECT) / "volumes" / name / "_data"
    path.mkdir(parents=True, exist_ok=True)
    (path / "state").write_text(payload)
    return path


plain = volume("plain", "plain-payload")
own = Path(SUBJECT) / "volumes" / "own" / "_data"
own.mkdir(parents=True, exist_ok=True)
shell(f"mount -t tmpfs tmpfs {own}")
(own / "state").write_text("own-payload")

check("a plain volume is captured", unsnapshotted(Backing(str(plain)), SUBJECT) is None)
check(
    "a volume on a mount of its own is not",
    unsnapshotted(Backing(str(own)), SUBJECT) is not None,
)
check(
    "a declared backing store is not, mounted or not",
    unsnapshotted(Backing(str(plain), options={"type": "nfs"}), SUBJECT) is not None,
)
check(
    "a foreign driver is not",
    unsnapshotted(Backing(str(plain), driver="rexray"), SUBJECT) is not None,
)

with volume_snapshot("btrfs", SUBJECT, "e2e", run=shell) as resolve:
    frozen_plain = Path(resolve(str(plain)))
    frozen_own = Path(resolve(str(own)))

    check(
        "the snapshot carries the plain volume",
        (frozen_plain / "state").read_text() == "plain-payload",
    )
    check(
        "the snapshot shows the other volume as an empty directory",
        frozen_own.is_dir() and not any(frozen_own.iterdir()),
    )

    source, reason = snapshot_source(resolve, Backing(str(plain)), SUBJECT)
    check(
        "the plain volume is read from the snapshot",
        source is not None and source.rstrip("/") == str(frozen_plain),
    )

    source, reason = snapshot_source(resolve, Backing(str(own)), SUBJECT)
    check(f"the other volume degrades to live: {reason[:60]}", source is None)

print("ALL OK", flush=True)
