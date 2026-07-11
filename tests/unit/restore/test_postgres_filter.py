import unittest

from baudolo.restore.db.postgres import filter_superuser_only_lines


def _filter(raw: bytes) -> bytes:
    return b"".join(filter_superuser_only_lines(raw.splitlines(keepends=True)))


class TestFilterSuperuserOnlyLines(unittest.TestCase):
    def test_drops_superuser_only_statements(self) -> None:
        raw = (
            b"CREATE TABLE t (id int);\n"
            b"COMMENT ON EXTENSION pg_trgm IS 'trigram';\n"
            b"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO x;\n"
            b"INSERT INTO t VALUES (1);\n"
        )
        self.assertEqual(
            _filter(raw),
            b"CREATE TABLE t (id int);\nINSERT INTO t VALUES (1);\n",
        )

    def test_copy_data_rows_are_never_filtered(self) -> None:
        raw = (
            b"COPY public.snippets (body) FROM stdin;\n"
            b"COMMENT ON EXTENSION looks like sql but is data\n"
            b"ALTER DEFAULT PRIVILEGES stored as text\n"
            b"\\.\n"
            b"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM y;\n"
        )
        self.assertEqual(
            _filter(raw),
            b"COPY public.snippets (body) FROM stdin;\n"
            b"COMMENT ON EXTENSION looks like sql but is data\n"
            b"ALTER DEFAULT PRIVILEGES stored as text\n"
            b"\\.\n",
        )

    def test_consecutive_copy_blocks_keep_state(self) -> None:
        raw = (
            b"COPY public.a (v) FROM stdin;\n"
            b"row-a\n"
            b"\\.\n"
            b"COMMENT ON EXTENSION dropme IS 'x';\n"
            b"COPY public.b (v) FROM stdin;\n"
            b"COMMENT ON EXTENSION kept-as-data\n"
            b"\\.\n"
        )
        out = _filter(raw)
        self.assertNotIn(b"dropme", out)
        self.assertIn(b"COMMENT ON EXTENSION kept-as-data\n", out)

    def test_everything_else_passes_through_verbatim(self) -> None:
        raw = (
            b"SET statement_timeout = 0;\n"
            b"CREATE EXTENSION IF NOT EXISTS pg_trgm;\n"
            b"GRANT ALL ON SCHEMA public TO app;\n"
        )
        self.assertEqual(_filter(raw), raw)


if __name__ == "__main__":
    unittest.main()
