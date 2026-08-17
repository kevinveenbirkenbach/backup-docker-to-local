from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from baudolo.generation import CLUSTER_SUFFIX, DUMP_SUFFIX, FILES_DIR, SQL_DIR


@dataclass(frozen=True)
class BackupPaths:
    volume_name: str
    backup_hash: str
    version: str
    repo_name: str
    backups_dir: str = "/Backups"

    def root(self) -> str:
        # Always build an absolute path under backups_dir
        return str(
            Path(self.backups_dir)
            / self.backup_hash
            / self.repo_name
            / self.version
            / self.volume_name
        )

    def files_dir(self) -> str:
        return str(Path(self.root()) / FILES_DIR)

    def sql_file(self, db_name: str) -> str:
        return str(Path(self.root()) / SQL_DIR / f"{db_name}{DUMP_SUFFIX}")

    def cluster_file(self, instance: str) -> str:
        """The pg_dumpall stream a `database = '*'` row produces."""
        return str(Path(self.root()) / SQL_DIR / f"{instance}{CLUSTER_SUFFIX}")
