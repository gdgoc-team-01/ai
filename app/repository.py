from typing import Literal

import psycopg
from psycopg.rows import class_row
from fastapi import HTTPException
from pgvector import Vector

from .config import Settings
from .schemas import Candidate, CategoryCode


def connect(settings: Settings):
    if settings.database_url is None:
        raise HTTPException(503, "AI service temporarily unavailable")
    return psycopg.connect(settings.database_url.get_secret_value(), connect_timeout=5)


def find_matches(
    settings: Settings, target_type: Literal["FOUND", "LOST"], embedding: list[float],
    category: CategoryCode, *, x: float, y: float, last_seen_at: str | None = None,
    noticed_missing_at: str | None = None, found_at: str | None = None,
) -> list[Candidate]:
    # Only these fixed SQL expressions vary by direction. Request values are bound below.
    if target_type == "FOUND":
        times = "%(last)s::timestamptz AS last_seen, %(end)s::timestamptz AS noticed, p.found_at AS found"
    else:
        times = "p.last_seen_at AS last_seen, p.noticed_missing_at AS noticed, %(found)s::timestamptz AS found"

    sql = f"""
        WITH candidates AS (
            SELECT p.id, {times}, e.embedding <=> %(query)s::vector AS cosine_distance,
                   point(p.location_x, p.location_y) <-> point(%(x)s, %(y)s) AS distance
              FROM posts p JOIN post_embeddings e ON e.post_id = p.id
             WHERE p.post_type = %(target)s AND p.status = 'OPEN'
               AND (%(category)s::text = 'OTHER' OR p.category IN (%(category)s, 'OTHER'))
        )
        SELECT id AS post_id,
               0.94 * (1 - cosine_distance / 2)
               + 0.03 * power(2::numeric, -greatest(0, extract(epoch FROM found - noticed)) / (48 * 3600))
               + 0.03 * power(2.0::float8, -distance / 200) AS score
          FROM candidates
         WHERE last_seen <= noticed AND found >= last_seen
           AND cosine_distance BETWEEN 0 AND 2 AND distance IS NOT NULL
         ORDER BY score DESC, id ASC
         LIMIT 20
    """
    params = {"query": Vector(embedding).to_text(), "target": target_type, "category": category,
              "x": x, "y": y, "last": last_seen_at, "end": noticed_missing_at, "found": found_at}
    with connect(settings) as connection, connection.cursor(row_factory=class_row(Candidate)) as cursor:
        return cursor.execute(sql, params).fetchall()
