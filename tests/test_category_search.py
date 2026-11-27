import os
from contextlib import nullcontext
from pathlib import Path
from unittest import TestCase, skipUnless
from unittest.mock import patch

import psycopg
from pgvector import Vector

from app.config import Settings
from app.repository import find_matches


QUERY = [1.0] + [0.0] * 767
START = "2026-11-27T00:00:00+09:00"
END = "2026-11-27T01:00:00+09:00"


@skipUnless(os.getenv("TEST_DATABASE_URL"), "Set TEST_DATABASE_URL to a test DB with pgvector")
class SearchTests(TestCase):
    def setUp(self):
        self.db = self.enterContext(psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True))
        self.db.execute("""CREATE TEMP TABLE posts (
            id bigint PRIMARY KEY, post_type text, status text DEFAULT 'OPEN',
            category varchar(30) DEFAULT 'UNKNOWN', last_seen_at timestamptz, noticed_missing_at timestamptz,
            found_at timestamptz, location_x float8, location_y float8)""")
        self.db.execute("CREATE TEMP TABLE post_embeddings (post_id bigint PRIMARY KEY, embedding vector(768))")
        self.db.execute("INSERT INTO posts(id) VALUES (0)")
        migration = Path(__file__).resolve().parents[1] / "sql/002_category_other.sql"
        self.db.execute(migration.read_text(encoding="utf8"))
        self.assertEqual(self.db.execute("SELECT category FROM posts WHERE id=0").fetchone(), ("OTHER",))
        self.db.execute("INSERT INTO posts(id) VALUES (-1)")
        self.assertEqual(self.db.execute("SELECT category FROM posts WHERE id=-1").fetchone(), ("OTHER",))
        self.enterContext(patch("app.repository.connect", return_value=nullcontext(self.db)))
        self.settings = Settings(_env_file=None)

    def add(self, key, kind="FOUND", category="BAG", found=END, x=0, y=0, vector=QUERY):
        self.db.execute("""INSERT INTO posts
            (id, post_type, category, last_seen_at, noticed_missing_at, found_at, location_x, location_y)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (key, kind, category, START if kind=="LOST" else None, END if kind=="LOST" else None,
             found if kind=="FOUND" else None, x, y))
        if vector is not None:
            self.db.execute("INSERT INTO post_embeddings VALUES (%s,%s::vector)", (key, Vector(vector).to_text()))

    def search(self, category="BAG"):
        return find_matches(self.settings, "FOUND", QUERY, category, x=0, y=0, last_seen_at=START, noticed_missing_at=END)

    def test_score_components_and_time_boundaries(self):
        self.add(1, found="2026-11-26T15:00:00Z")
        self.add(2, found="2026-11-27T00:30:00+09:00")
        self.add(3, found=END)
        self.add(4, found="2026-11-26T14:59:59Z")
        self.add(5, found="2026-11-29T01:00:00+09:00")
        self.add(6, x=120, y=160)
        self.add(7, vector=[-1.0]+QUERY[1:])
        self.add(8, x=120, y=160, found="2026-11-29T01:00:00+09:00", vector=[0,1]+QUERY[2:])
        self.add(9, kind="LOST", vector=[0,1]+QUERY[2:])
        rows = self.search()
        self.assertEqual([r.post_id for r in rows], [1,2,3,5,6,8,7])
        for r, expected in zip(rows, [1,1,1,.985,.985,.5,.06], strict=True):
            self.assertAlmostEqual(r.score, expected)
        reverse = find_matches(self.settings, "LOST", QUERY, "BAG", x=120, y=160,
                               found_at="2026-11-29T01:00:00+09:00")
        self.assertEqual([r.post_id for r in reverse], [9])
        self.assertAlmostEqual(reverse[0].score, rows[-2].score)
        self.assertFalse(find_matches(self.settings, "LOST", QUERY, "OTHER", x=0, y=0,
                                      found_at="2026-11-26T14:59:59Z"))

    def test_score_before_limit(self):
        for i in range(1,21):
            self.add(i, x=1000, found="2026-12-10T12:00:00+09:00")
        self.add(21, vector=[0.99,0.1]+QUERY[2:])
        self.assertEqual([r.post_id for r in self.search()], [21,*range(1,20)])

    def test_category_and_invalid_candidates(self):
        self.add(1)
        self.add(2, category="OTHER")
        self.add(3, category="WALLET")
        self.add(4, vector=None)
        self.add(5, vector=[0]*768)
        self.add(6, found=None)
        self.add(7, x=None)
        self.add(8)
        self.db.execute("UPDATE posts SET status='RESOLVED' WHERE id=8")
        self.assertEqual([r.post_id for r in self.search()], [1,2])
        self.assertEqual([r.post_id for r in self.search("OTHER")], [1,2,3])
