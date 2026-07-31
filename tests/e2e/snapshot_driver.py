"""Exercise volume_snapshot against a real filesystem, from inside a container.

Runs where loop devices exist. Prints one PASS/FAIL line per assertion and exits
non-zero on the first failure, so the calling test can surface the reason.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/src")

from baudolo.backup.snapshot import SnapshotError, volume_snapshot  # noqa: E402

KIND = sys.argv[1]
SUBJECT = sys.argv[2]
EXPECT = sys.argv[3]


def shell(command: str) -> list[str]:
    proc = subprocess.run(command, shell=True, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SnapshotError(f"{command} exited {proc.returncode}: {proc.stderr.strip()}")
    return proc.stdout.splitlines()


def check(label: str, condition: bool) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}", flush=True)
    if not condition:
        sys.exit(1)


volume = Path(SUBJECT) / "volumes" / "demo" / "_data"
volume.mkdir(parents=True, exist_ok=True)
(volume / "state").write_text("before\n")

if EXPECT == "unsupported":
    try:
        with volume_snapshot(KIND, SUBJECT, "e2e", run=shell):
            check("snapshot on an unsupported filesystem must not succeed", False)
    except SnapshotError as exc:
        check(f"refused loudly: {str(exc)[:60]}", True)
    sys.exit(0)

with volume_snapshot(KIND, SUBJECT, "e2e", run=shell) as resolve:
    frozen = Path(resolve(str(volume))) / "state"
    check("the snapshot exposes the volume", frozen.is_file())
    check("the snapshot carries the content", frozen.read_text() == "before\n")

    (volume / "state").write_text("after\n")
    check("a later write does not reach the snapshot", frozen.read_text() == "before\n")
    check("the live tree did change", (volume / "state").read_text() == "after\n")

    root = Path(resolve(SUBJECT))

check("the snapshot is removed afterwards", not root.exists() or not (root / "volumes").exists())
print("ALL OK", flush=True)
