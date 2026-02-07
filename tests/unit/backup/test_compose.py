from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from typing import List
from unittest.mock import patch


def _touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)

    # If the path already exists as a directory (e.g. ".env" created by ".env/env"),
    # remove it so we can create a file with the same name.
    if p.exists() and p.is_dir():
        shutil.rmtree(p)

    p.write_text("x", encoding="utf-8")


def _setup_compose_dir(
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

    _touch(d / compose_name)

    if with_override:
        _touch(d / "docker-compose.override.yml")

    if with_ca_override:
        _touch(d / "docker-compose.ca.override.yml")

    if env_layout == ".env":
        _touch(d / ".env")
    elif env_layout == ".env/env":
        _touch(d / ".env" / "env")

    return d


class TestCompose(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from baudolo.backup import compose as mod

        cls.compose_mod = mod

    def test_find_compose_file_supports_all_valid_names_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)

            variants = [
                "compose.yml",
                "compose.yaml",
                "docker-compose.yml",
                "docker-compose.yaml",
                "docker-compose.yAml",
            ]

            for i, name in enumerate(variants):
                d = _setup_compose_dir(
                    tmp_path,
                    name=f"project{i}",
                    compose_name=name,
                )
                found = self.compose_mod._find_compose_file(str(d))
                self.assertIsNotNone(found)
                self.assertEqual(found.name, name)

    def test_find_compose_file_returns_none_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            d = tmp_path / "empty"
            d.mkdir(parents=True, exist_ok=True)

            found = self.compose_mod._find_compose_file(str(d))
            self.assertIsNone(found)

    def test_build_cmd_uses_wrapper_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            d = _setup_compose_dir(
                tmp_path,
                with_override=True,
                with_ca_override=True,
                env_layout=".env",
            )

            def fake_which(name: str):
                if name == "compose":
                    return "/usr/local/bin/compose"
                return None

            with patch.object(self.compose_mod.shutil, "which", fake_which):
                cmd = self.compose_mod._build_compose_cmd(str(d), ["up", "-d"])

            self.assertEqual(
                cmd,
                [
                    "/usr/local/bin/compose",
                    "--chdir",
                    str(d.resolve()),
                    "--",
                    "up",
                    "-d",
                ],
            )

    def test_build_cmd_fallback_uses_plain_docker_compose_chdir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            d = _setup_compose_dir(
                tmp_path,
                with_override=True,
                with_ca_override=True,
                env_layout=".env",
            )

            def fake_which(name: str):
                if name == "compose":
                    return None
                if name == "docker":
                    return "/usr/bin/docker"
                return None

            with patch.object(self.compose_mod.shutil, "which", fake_which):
                cmd = self.compose_mod._build_compose_cmd(
                    str(d), ["up", "-d", "--force-recreate"]
                )

            expected: List[str] = [
                "/usr/bin/docker",
                "compose",
                "--chdir",
                str(d.resolve()),
                "up",
                "-d",
                "--force-recreate",
            ]
            self.assertEqual(cmd, expected)

    def test_hard_restart_calls_run_twice_with_correct_cmds_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            d = _setup_compose_dir(tmp_path, name="mailu", env_layout=".env")

            def fake_which(name: str):
                if name == "compose":
                    return "/usr/local/bin/compose"
                return None

            with patch.object(self.compose_mod.shutil, "which", fake_which):
                calls = []

                def fake_run(cmd, check: bool):
                    calls.append((cmd, check))
                    return 0

                with patch.object(self.compose_mod.subprocess, "run", fake_run):
                    self.compose_mod.hard_restart_docker_services(str(d))

            self.assertEqual(
                calls,
                [
                    (
                        [
                            "/usr/local/bin/compose",
                            "--chdir",
                            str(d.resolve()),
                            "--",
                            "down",
                        ],
                        True,
                    ),
                    (
                        [
                            "/usr/local/bin/compose",
                            "--chdir",
                            str(d.resolve()),
                            "--",
                            "up",
                            "-d",
                        ],
                        True,
                    ),
                ],
            )

    def test_hard_restart_calls_run_twice_with_correct_cmds_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            d = _setup_compose_dir(
                tmp_path,
                name="mailu",
                with_override=True,
                with_ca_override=True,
                env_layout=".env/env",
            )

            def fake_which(name: str):
                if name == "compose":
                    return None
                if name == "docker":
                    return "/usr/bin/docker"
                return None

            with patch.object(self.compose_mod.shutil, "which", fake_which):
                calls = []

                def fake_run(cmd, check: bool):
                    calls.append((cmd, check))
                    return 0

                with patch.object(self.compose_mod.subprocess, "run", fake_run):
                    self.compose_mod.hard_restart_docker_services(str(d))

            self.assertEqual(
                calls,
                [
                    (
                        [
                            "/usr/bin/docker",
                            "compose",
                            "--chdir",
                            str(d.resolve()),
                            "down",
                        ],
                        True,
                    ),
                    (
                        [
                            "/usr/bin/docker",
                            "compose",
                            "--chdir",
                            str(d.resolve()),
                            "up",
                            "-d",
                        ],
                        True,
                    ),
                ],
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
