from __future__ import annotations

from pathlib import Path
from typing import List

import pytest


@pytest.fixture
def compose_mod():
    """
    Import the module under test.
    Adjust the import path if your package layout differs.
    """
    from baudolo.backup import compose as mod

    return mod


def _touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")


def _setup_compose_dir(
    tmp_path: Path,
    name: str = "mailu",
    *,
    with_override: bool = False,
    with_ca_override: bool = False,
    env_layout: str | None = None,  # None | ".env" | ".env/env"
) -> Path:
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)

    _touch(d / "docker-compose.yml")

    if with_override:
        _touch(d / "docker-compose.override.yml")

    if with_ca_override:
        _touch(d / "docker-compose.ca.override.yml")

    if env_layout == ".env":
        _touch(d / ".env")
    elif env_layout == ".env/env":
        _touch(d / ".env" / "env")

    return d


def test_detect_env_file_prefers_dotenv_over_legacy(tmp_path: Path, compose_mod):
    d = _setup_compose_dir(tmp_path, env_layout=".env/env")
    # Also create .env file -> should be preferred
    _touch(d / ".env")

    env_file = compose_mod._detect_env_file(d)
    assert env_file == d / ".env"


def test_detect_env_file_uses_legacy_if_no_dotenv(tmp_path: Path, compose_mod):
    d = _setup_compose_dir(tmp_path, env_layout=".env/env")
    env_file = compose_mod._detect_env_file(d)
    assert env_file == d / ".env" / "env"


def test_detect_compose_files_requires_base(tmp_path: Path, compose_mod):
    d = tmp_path / "stack"
    d.mkdir()

    with pytest.raises(FileNotFoundError):
        compose_mod._detect_compose_files(d)


def test_detect_compose_files_includes_optional_overrides(tmp_path: Path, compose_mod):
    d = _setup_compose_dir(
        tmp_path,
        with_override=True,
        with_ca_override=True,
    )

    files = compose_mod._detect_compose_files(d)
    assert files == [
        d / "docker-compose.yml",
        d / "docker-compose.override.yml",
        d / "docker-compose.ca.override.yml",
    ]


def test_build_cmd_uses_wrapper_when_present(monkeypatch, tmp_path: Path, compose_mod):
    d = _setup_compose_dir(
        tmp_path, with_override=True, with_ca_override=True, env_layout=".env"
    )

    # Pretend "which compose" finds a wrapper.
    monkeypatch.setattr(
        compose_mod.shutil, "which", lambda name: "/usr/local/bin/compose"
    )

    cmd = compose_mod._build_compose_cmd(str(d), ["up", "-d"])

    # Wrapper should be used, and wrapper itself resolves -f / --env-file.
    assert cmd == [
        "/usr/local/bin/compose",
        "--chdir",
        str(d.resolve()),
        "--",
        "up",
        "-d",
    ]


def test_build_cmd_fallback_docker_compose_with_all_files_and_env(
    monkeypatch, tmp_path: Path, compose_mod
):
    d = _setup_compose_dir(
        tmp_path,
        with_override=True,
        with_ca_override=True,
        env_layout=".env",
    )

    # No wrapper found.
    monkeypatch.setattr(compose_mod.shutil, "which", lambda name: None)

    cmd = compose_mod._build_compose_cmd(str(d), ["up", "-d", "--force-recreate"])

    # Fallback should replicate the wrapper resolution logic.
    expected: List[str] = [
        "docker",
        "compose",
        "-f",
        str((d / "docker-compose.yml").resolve()),
        "-f",
        str((d / "docker-compose.override.yml").resolve()),
        "-f",
        str((d / "docker-compose.ca.override.yml").resolve()),
        "--env-file",
        str((d / ".env").resolve()),
        "up",
        "-d",
        "--force-recreate",
    ]
    assert cmd == expected


def test_hard_restart_calls_run_twice_with_correct_cmds_wrapper(
    monkeypatch, tmp_path: Path, compose_mod
):
    d = _setup_compose_dir(tmp_path, name="mailu", env_layout=".env")

    # Wrapper exists
    monkeypatch.setattr(
        compose_mod.shutil, "which", lambda name: "/usr/local/bin/compose"
    )

    calls = []

    def fake_run(cmd, check: bool):
        calls.append((cmd, check))
        return 0

    monkeypatch.setattr(compose_mod.subprocess, "run", fake_run)

    compose_mod.hard_restart_docker_services(str(d))

    assert calls == [
        (["/usr/local/bin/compose", "--chdir", str(d.resolve()), "--", "down"], True),
        (
            ["/usr/local/bin/compose", "--chdir", str(d.resolve()), "--", "up", "-d"],
            True,
        ),
    ]


def test_hard_restart_calls_run_twice_with_correct_cmds_fallback(
    monkeypatch, tmp_path: Path, compose_mod
):
    d = _setup_compose_dir(
        tmp_path,
        name="mailu",
        with_override=True,
        with_ca_override=True,
        env_layout=".env/env",
    )

    # No wrapper exists
    monkeypatch.setattr(compose_mod.shutil, "which", lambda name: None)

    calls = []

    def fake_run(cmd, check: bool):
        calls.append((cmd, check))
        return 0

    monkeypatch.setattr(compose_mod.subprocess, "run", fake_run)

    compose_mod.hard_restart_docker_services(str(d))

    # We assert only key structure + ordering to keep it robust.
    down_cmd = calls[0][0]
    up_cmd = calls[1][0]

    assert calls[0][1] is True
    assert calls[1][1] is True

    # down: docker compose -f ... --env-file ... down
    assert down_cmd[0:2] == ["docker", "compose"]
    assert down_cmd[-1] == "down"
    assert "--env-file" in down_cmd

    # up: docker compose ... up -d
    assert up_cmd[0:2] == ["docker", "compose"]
    assert up_cmd[-2:] == ["up", "-d"] or up_cmd[-3:] == ["up", "-d"]  # tolerance
    assert "--env-file" in up_cmd
