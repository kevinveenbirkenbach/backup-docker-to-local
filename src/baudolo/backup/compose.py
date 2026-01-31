from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional


def _detect_env_file(project_dir: Path) -> Optional[Path]:
    """
    Detect Compose env file in a directory.
    Preference (same as Infinito.Nexus wrapper):
      1) <dir>/.env (file)
      2) <dir>/.env/env (file)  (legacy layout)
    """
    c1 = project_dir / ".env"
    if c1.is_file():
        return c1

    c2 = project_dir / ".env" / "env"
    if c2.is_file():
        return c2

    return None


def _detect_compose_files(project_dir: Path) -> List[Path]:
    """
    Detect Compose file stack in a directory (same as Infinito.Nexus wrapper).
    Always requires docker-compose.yml.
    Optionals:
      - docker-compose.override.yml
      - docker-compose.ca.override.yml
    """
    base = project_dir / "docker-compose.yml"
    if not base.is_file():
        raise FileNotFoundError(f"Missing docker-compose.yml in: {project_dir}")

    files = [base]

    override = project_dir / "docker-compose.override.yml"
    if override.is_file():
        files.append(override)

    ca_override = project_dir / "docker-compose.ca.override.yml"
    if ca_override.is_file():
        files.append(ca_override)

    return files


def _compose_wrapper_path() -> Optional[str]:
    """
    Prefer the Infinito.Nexus compose wrapper if present.
    Equivalent to: `which compose`
    """
    return shutil.which("compose")


def _build_compose_cmd(project_dir: str, passthrough: List[str]) -> List[str]:
    """
    Build the compose command for this project directory.

    Behavior:
    - If `compose` wrapper exists: use it with --chdir (so it resolves -f/--env-file itself)
    - Else: use `docker compose` and replicate wrapper's file/env detection.
    """
    pdir = Path(project_dir).resolve()

    wrapper = _compose_wrapper_path()
    if wrapper:
        # Wrapper defaults project name to basename of --chdir.
        # "--" ensures wrapper stops parsing its own args.
        return [wrapper, "--chdir", str(pdir), "--", *passthrough]

    # Fallback: pure docker compose, but mirror wrapper behavior.
    files = _detect_compose_files(pdir)
    env_file = _detect_env_file(pdir)

    cmd: List[str] = ["docker", "compose"]
    for f in files:
        cmd += ["-f", str(f)]
    if env_file:
        cmd += ["--env-file", str(env_file)]

    cmd += passthrough
    return cmd


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
