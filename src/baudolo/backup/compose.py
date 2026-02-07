from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional


def _build_compose_cmd(project_dir: str, passthrough: List[str]) -> List[str]:
    """
    Build the compose command for this project directory.

    Policy:
    - If `compose` wrapper exists (Infinito.Nexus): use it and delegate ALL logic to it.
    - Else: use plain `docker compose` with --chdir.
    - NO custom compose file/env detection in this project.
    """
    pdir = Path(project_dir).resolve()

    wrapper = shutil.which("compose")
    if wrapper:
        # "--" ensures wrapper stops parsing its own args.
        return [wrapper, "--chdir", str(pdir), "--", *passthrough]

    docker = shutil.which("docker")
    if docker:
        return [docker, "compose", "--chdir", str(pdir), *passthrough]

    raise RuntimeError("Neither 'compose' nor 'docker' found in PATH")


def _find_compose_file(project_dir: str) -> Optional[Path]:
    """
    Detect a compose file in `project_dir` (case-insensitive).

    Supported names:
    - compose.yml / compose.yaml
    - docker-compose.yml / docker-compose.yaml
    """
    pdir = Path(project_dir)
    if not pdir.is_dir():
        return None

    # Map lowercase filename -> actual Path (preserves original casing)
    by_lower = {p.name.lower(): p for p in pdir.iterdir() if p.is_file()}

    # Preferred order (policy decision)
    candidates = [
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    ]

    for name in candidates:
        found = by_lower.get(name)
        if found is not None:
            return found

    return None


def hard_restart_docker_services(dir_path: str) -> None:
    print(f"Hard restart compose services in: {dir_path}", flush=True)

    down_cmd = _build_compose_cmd(dir_path, ["down"])
    up_cmd = _build_compose_cmd(dir_path, ["up", "-d"])

    print(">>> " + " ".join(down_cmd), flush=True)
    subprocess.run(down_cmd, check=True)

    print(">>> " + " ".join(up_cmd), flush=True)
    subprocess.run(up_cmd, check=True)


def handle_docker_compose_services(
    parent_directory: str,
    hard_restart_required: list[str],
) -> None:
    for entry in os.scandir(parent_directory):
        if not entry.is_dir():
            continue

        dir_path = entry.path
        name = os.path.basename(dir_path)

        print(f"Checking directory: {dir_path}", flush=True)

        compose_file = _find_compose_file(dir_path)
        if compose_file is None:
            print("No supported compose file found. Skipping.", flush=True)
            continue

        if name in hard_restart_required:
            print(f"{name}: hard restart required.", flush=True)
            hard_restart_docker_services(dir_path)
        else:
            print(f"{name}: no restart required.", flush=True)
