from __future__ import annotations

import os
import subprocess


def hard_restart_docker_services(dir_path: str) -> None:
    print(f"Hard restart docker-compose services in: {dir_path}", flush=True)
    subprocess.run(["docker-compose", "down"], cwd=dir_path, check=True)
    subprocess.run(["docker-compose", "up", "-d"], cwd=dir_path, check=True)


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
