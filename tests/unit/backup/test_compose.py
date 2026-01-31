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


class TestCompose(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from baudolo.backup import compose as mod

        cls.compose_mod = mod

    def test_detect_env_file_prefers_dotenv_over_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            d = _setup_compose_dir(tmp_path, env_layout=".env/env")
            # Also create .env file -> should be preferred
            _touch(d / ".env")

            env_file = self.compose_mod._detect_env_file(d)
            self.assertEqual(env_file, d / ".env")

    def test_detect_env_file_uses_legacy_if_no_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            d = _setup_compose_dir(tmp_path, env_layout=".env/env")

            env_file = self.compose_mod._detect_env_file(d)
            self.assertEqual(env_file, d / ".env" / "env")

    def test_detect_compose_files_requires_base(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            d = tmp_path / "stack"
            d.mkdir()

            with self.assertRaises(FileNotFoundError):
                self.compose_mod._detect_compose_files(d)

    def test_detect_compose_files_includes_optional_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            d = _setup_compose_dir(
                tmp_path,
                with_override=True,
                with_ca_override=True,
            )

            files = self.compose_mod._detect_compose_files(d)
            self.assertEqual(
                files,
                [
                    d / "docker-compose.yml",
                    d / "docker-compose.override.yml",
                    d / "docker-compose.ca.override.yml",
                ],
            )

    def test_build_cmd_uses_wrapper_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            d = _setup_compose_dir(
                tmp_path, with_override=True, with_ca_override=True, env_layout=".env"
            )

            with patch.object(
                self.compose_mod.shutil, "which", lambda name: "/usr/local/bin/compose"
            ):
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

    def test_build_cmd_fallback_docker_compose_with_all_files_and_env(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            d = _setup_compose_dir(
                tmp_path,
                with_override=True,
                with_ca_override=True,
                env_layout=".env",
            )

            with patch.object(self.compose_mod.shutil, "which", lambda name: None):
                cmd = self.compose_mod._build_compose_cmd(
                    str(d), ["up", "-d", "--force-recreate"]
                )

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
            self.assertEqual(cmd, expected)

    def test_hard_restart_calls_run_twice_with_correct_cmds_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            d = _setup_compose_dir(tmp_path, name="mailu", env_layout=".env")

            with patch.object(
                self.compose_mod.shutil, "which", lambda name: "/usr/local/bin/compose"
            ):
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

            with patch.object(self.compose_mod.shutil, "which", lambda name: None):
                calls = []

                def fake_run(cmd, check: bool):
                    calls.append((cmd, check))
                    return 0

                with patch.object(self.compose_mod.subprocess, "run", fake_run):
                    self.compose_mod.hard_restart_docker_services(str(d))

            down_cmd = calls[0][0]
            up_cmd = calls[1][0]

            self.assertTrue(calls[0][1] is True)
            self.assertTrue(calls[1][1] is True)

            self.assertEqual(down_cmd[0:2], ["docker", "compose"])
            self.assertEqual(down_cmd[-1], "down")
            self.assertIn("--env-file", down_cmd)

            self.assertEqual(up_cmd[0:2], ["docker", "compose"])
            self.assertTrue(up_cmd[-2:] == ["up", "-d"] or up_cmd[-3:] == ["up", "-d"])
            self.assertIn("--env-file", up_cmd)


if __name__ == "__main__":
    unittest.main(verbosity=2)
