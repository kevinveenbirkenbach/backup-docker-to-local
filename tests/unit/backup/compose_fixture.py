"""Builds the on-disk compose directories the compose tests discover."""

from __future__ import annotations

import shutil
from pathlib import Path


def touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)

    # ".env/env" leaves ".env" behind as a directory, which blocks a later ".env" file.
    if p.exists() and p.is_dir():
        shutil.rmtree(p)

    p.write_text("x", encoding="utf-8")


def setup_compose_dir(
    tmp_path: Path,
    name: str = "mailu",
    *,
    compose_name: str = "docker-compose.yml",
    with_override: bool = False,
    with_ca_override: bool = False,
    env_layout: str | None = None,  # None | ".env" | ".env/env"
) -> Path:
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)

    touch(d / compose_name)

    if with_override:
        touch(d / "docker-compose.override.yml")

    if with_ca_override:
        touch(d / "docker-compose.ca.override.yml")

    if env_layout == ".env":
        touch(d / ".env")
    elif env_layout == ".env/env":
        touch(d / ".env" / "env")

    return d
