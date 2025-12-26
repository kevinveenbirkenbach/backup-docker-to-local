import unittest
from unittest.mock import patch

from baudolo.backup.app import requires_stop


class TestRequiresStop(unittest.TestCase):
    @patch("baudolo.backup.app.get_image_info")
    def test_requires_stop_false_when_all_images_are_whitelisted(self, mock_get_image_info):
        # All containers use images containing allowed substrings
        mock_get_image_info.side_effect = [
            "repo/mastodon:v4",
            "repo/wordpress:latest",
        ]
        containers = ["c1", "c2"]
        whitelist = ["mastodon", "wordpress"]
        self.assertFalse(requires_stop(containers, whitelist))

    @patch("baudolo.backup.app.get_image_info")
    def test_requires_stop_true_when_any_image_is_not_whitelisted(self, mock_get_image_info):
        mock_get_image_info.side_effect = [
            "repo/mastodon:v4",
            "repo/nginx:latest",
        ]
        containers = ["c1", "c2"]
        whitelist = ["mastodon", "wordpress"]
        self.assertTrue(requires_stop(containers, whitelist))

    @patch("baudolo.backup.app.get_image_info")
    def test_requires_stop_true_when_whitelist_empty(self, mock_get_image_info):
        mock_get_image_info.return_value = "repo/anything:latest"
        self.assertTrue(requires_stop(["c1"], []))


if __name__ == "__main__":
    unittest.main()
