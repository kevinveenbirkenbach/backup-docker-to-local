from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import List


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


def hard_restart_docker_services(dir_path: str) -> None:
    print(f"Hard restart compose services in: {dir_path}", flush=True)

    down_cmd = _build_compose_cmd(dir_path, ["down"])
    up_cmd = _build_compose_cmd(dir_path, ["up", "-d"])

    print(">>> " + " ".join(down_cmd), flush=True)
    subprocess.run(down_cmd, check=True)

    print(">>> " + " ".join(up_cmd), flush=True)
    subprocess.run(up_cmd, check=True)


def handle_docker_compose_services(
    parent_directory: str, hard_restart_required: list[str]
) -> None:
    for entry in os.scandir(parent_directory):
        if not entry.is_dir():
            continue

        dir_path = entry.path
        name = os.path.basename(dir_path)
        compose_file = os.path.join(dir_path, "docker-compose.yml")

        print(f"Checking directory: {dir_path}", flush=True)
        if not os.path.isfile(compose_file):
            print("No docker-compose.yml found. Skipping.", flush=True)
            continue

        if name in hard_restart_required:
            print(f"{name}: hard restart required.", flush=True)
            hard_restart_docker_services(dir_path)
        else:
            print(f"{name}: no restart required.", flush=True)
