import unittest
from unittest.mock import patch

from baudolo.backup.app import requires_stop


@patch("baudolo.backup.app.is_swarm_task", return_value=False)
class TestRequiresStop(unittest.TestCase):
    @patch("baudolo.backup.app.get_image_info")
    def test_requires_stop_false_when_all_images_are_whitelisted(
        self, mock_get_image_info, _mock_is_swarm_task
    ):
        mock_get_image_info.side_effect = [
            "repo/mastodon:v4",
            "repo/wordpress:latest",
        ]
        containers = ["c1", "c2"]
        whitelist = ["repo/mastodon:v4", "repo/wordpress:latest"]
        self.assertFalse(requires_stop(containers, whitelist))

    @patch("baudolo.backup.app.get_image_info")
    def test_requires_stop_true_when_any_image_is_not_whitelisted(
        self, mock_get_image_info, _mock_is_swarm_task
    ):
        mock_get_image_info.side_effect = [
            "repo/mastodon:v4",
            "repo/nginx:latest",
        ]
        containers = ["c1", "c2"]
        whitelist = ["repo/mastodon:v4", "repo/wordpress:latest"]
        self.assertTrue(requires_stop(containers, whitelist))

    @patch("baudolo.backup.app.get_image_info")
    def test_requires_stop_true_on_substring_only_match(
        self, mock_get_image_info, _mock_is_swarm_task
    ):
        mock_get_image_info.return_value = "reg:5000/repo/mastodon:v4"
        self.assertTrue(requires_stop(["c1"], ["mastodon"]))
        self.assertTrue(requires_stop(["c1"], ["repo/mastodon:v4"]))

    @patch("baudolo.backup.app.get_image_info")
    def test_requires_stop_true_when_whitelist_empty(
        self, mock_get_image_info, _mock_is_swarm_task
    ):
        mock_get_image_info.return_value = "repo/anything:latest"
        self.assertTrue(requires_stop(["c1"], []))


class TestRequiresStopSwarm(unittest.TestCase):
    @patch("baudolo.backup.app.get_image_info")
    @patch("baudolo.backup.app.is_swarm_task", return_value=True)
    def test_swarm_tasks_never_require_stop(
        self, _mock_is_swarm_task, mock_get_image_info
    ):
        mock_get_image_info.return_value = "repo/not-whitelisted:latest"
        self.assertFalse(requires_stop(["c1"], []))
        mock_get_image_info.assert_not_called()


if __name__ == "__main__":
    unittest.main()
