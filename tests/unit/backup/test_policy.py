"""Contract of the rules deciding what is backed up and what must stop."""

from __future__ import annotations

import unittest
from unittest import mock

from baudolo.backup import policy as mod


class TestIsImageIgnored(unittest.TestCase):
    def test_an_empty_whitelist_ignores_nothing(self) -> None:
        self.assertFalse(mod.is_image_ignored("c1", []))

    def test_a_listed_image_is_ignored(self) -> None:
        with mock.patch.object(mod, "get_image_info", return_value="alpine:3.20"):
            self.assertTrue(mod.is_image_ignored("c1", ["alpine:3.20"]))

    def test_matching_is_exact(self) -> None:
        with mock.patch.object(mod, "get_image_info", return_value="alpine:3.21"):
            self.assertFalse(mod.is_image_ignored("c1", ["alpine:3.20"]))


class TestVolumeIsFullyIgnored(unittest.TestCase):
    def test_a_volume_without_containers_is_kept(self) -> None:
        self.assertFalse(mod.volume_is_fully_ignored([], ["alpine:3.20"]))

    def test_it_needs_every_container_to_be_ignored(self) -> None:
        with mock.patch.object(mod, "get_image_info", side_effect=["a", "b"]):
            self.assertFalse(mod.volume_is_fully_ignored(["c1", "c2"], ["a"]))

    def test_all_ignored_skips_the_volume(self) -> None:
        with mock.patch.object(mod, "get_image_info", side_effect=["a", "a"]):
            self.assertTrue(mod.volume_is_fully_ignored(["c1", "c2"], ["a"]))


class TestRequiresStop(unittest.TestCase):
    def test_no_containers_means_no_stop(self) -> None:
        self.assertFalse(mod.requires_stop([], []))

    def test_a_swarm_task_never_forces_a_stop(self) -> None:
        with mock.patch.object(mod, "is_swarm_task", return_value=True):
            self.assertFalse(mod.requires_stop(["c1"], []))

    def test_a_whitelisted_image_does_not_force_a_stop(self) -> None:
        with (
            mock.patch.object(mod, "is_swarm_task", return_value=False),
            mock.patch.object(mod, "get_image_info", return_value="alpine:3.20"),
        ):
            self.assertFalse(mod.requires_stop(["c1"], ["alpine:3.20"]))

    def test_an_unlisted_image_forces_a_stop(self) -> None:
        with (
            mock.patch.object(mod, "is_swarm_task", return_value=False),
            mock.patch.object(mod, "get_image_info", return_value="postgres:17"),
        ):
            self.assertTrue(mod.requires_stop(["c1"], ["alpine:3.20"]))

    def test_one_unlisted_container_is_enough(self) -> None:
        with (
            mock.patch.object(mod, "is_swarm_task", return_value=False),
            mock.patch.object(mod, "get_image_info", side_effect=["alpine:3.20", "x"]),
        ):
            self.assertTrue(mod.requires_stop(["c1", "c2"], ["alpine:3.20"]))


if __name__ == "__main__":
    unittest.main()
