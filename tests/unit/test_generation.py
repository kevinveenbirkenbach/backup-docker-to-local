"""Contract of the generation manifest document and the file it lands in."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from baudolo.backup.dumps import VolumeOutcome
from baudolo.backup.layout import write_manifest
from baudolo.generation import (
    CLUSTER_SUFFIX,
    DUMP_SUFFIX,
    FILES_DIR,
    MANIFEST_FILE,
    MANIFEST_SCHEMA,
    SQL_DIR,
    manifest_document,
)


class TestManifestDocument(unittest.TestCase):
    def test_it_states_the_layout_a_reader_needs(self) -> None:
        document = manifest_document({})
        self.assertEqual(
            document["layout"],
            {
                "files_dir": FILES_DIR,
                "sql_dir": SQL_DIR,
                "dump_suffix": DUMP_SUFFIX,
                "cluster_suffix": CLUSTER_SUFFIX,
            },
        )

    def test_it_carries_a_schema_so_a_reader_can_refuse_a_newer_one(self) -> None:
        self.assertEqual(manifest_document({})["schema"], MANIFEST_SCHEMA)

    def test_it_sorts_volumes_so_two_runs_produce_the_same_bytes(self) -> None:
        state = VolumeOutcome(database=False, dumped=False)
        document = manifest_document({"b": state, "a": state})
        self.assertEqual(list(document["volumes"]), ["a", "b"])


class TestWriteManifest(unittest.TestCase):
    def test_it_writes_readable_json_next_to_the_volumes(self) -> None:
        with tempfile.TemporaryDirectory() as version_dir:
            path = write_manifest(
                version_dir,
                {
                    "pgdata": VolumeOutcome(
                        database=True, dumped=False, engine="postgres"
                    )
                },
            )
            self.assertEqual(Path(path).name, MANIFEST_FILE)
            document = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(
            document["volumes"]["pgdata"],
            {"database": True, "dumped": False, "engine": "postgres"},
        )


if __name__ == "__main__":
    unittest.main()
