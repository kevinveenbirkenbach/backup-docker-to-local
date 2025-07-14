# tests/unit/test_backup.py

import unittest
from unittest.mock import patch
import importlib.util
import sys
import os
import pathlib

# Prevent actual directory creation in backup script import
dummy_mkdir = lambda self, *args, **kwargs: None
original_mkdir = pathlib.Path.mkdir
pathlib.Path.mkdir = dummy_mkdir

# Create a virtual databases.csv in the project root for the module import
test_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(test_dir, '../../'))
sys.path.insert(0, project_root)
db_csv_path = os.path.join(project_root, 'databases.csv')
with open(db_csv_path, 'w') as f:
    f.write('instance;database;username;password\n')

# Dynamically load the hyphenated script as module 'backup'
script_path = os.path.join(project_root, 'backup-docker-to-local.py')
spec = importlib.util.spec_from_file_location('backup', script_path)
backup = importlib.util.module_from_spec(spec)
sys.modules['backup'] = backup
spec.loader.exec_module(backup)

# Restore original mkdir
pathlib.Path.mkdir = original_mkdir

class TestIsImageWhitelisted(unittest.TestCase):
    @patch('backup.get_image_info')
    def test_returns_true_when_image_matches(self, mock_get_image_info):
        # Simulate a container image containing 'mastodon'
        mock_get_image_info.return_value = ['repo/mastodon:v4']
        images = ['mastodon', 'wordpress']
        self.assertTrue(
            backup.is_image_whitelisted('any_container', images),
            "Should return True when at least one image substring matches"
        )

    @patch('backup.get_image_info')
    def test_returns_false_when_no_image_matches(self, mock_get_image_info):
        # Simulate a container image without matching substrings
        mock_get_image_info.return_value = ['repo/nginx:latest']
        images = ['mastodon', 'wordpress']
        self.assertFalse(
            backup.is_image_whitelisted('any_container', images),
            "Should return False when no image substring matches"
        )

    @patch('backup.get_image_info')
    def test_returns_false_with_empty_image_list(self, mock_get_image_info):
        # Even if get_image_info returns something, an empty list yields False
        mock_get_image_info.return_value = ['repo/element:1.0']
        self.assertFalse(
            backup.is_image_whitelisted('any_container', []),
            "Should return False when the images list is empty"
        )

if __name__ == '__main__':
    unittest.main()
