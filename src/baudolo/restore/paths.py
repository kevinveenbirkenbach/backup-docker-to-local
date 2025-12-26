from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BackupPaths:
    volume_name: str
    backup_hash: str
    version: str
    repo_name: str
    backups_dir: str = "/Backups"

    def root(self) -> str:
        # Always build an absolute path under backups_dir
        return os.path.join(
            self.backups_dir,
            self.backup_hash,
            self.repo_name,
            self.version,
            self.volume_name,
        )

    def files_dir(self) -> str:
        return os.path.join(self.root(), "files")

    def sql_file(self, db_name: str) -> str:
        return os.path.join(self.root(), "sql", f"{db_name}.backup.sql")
