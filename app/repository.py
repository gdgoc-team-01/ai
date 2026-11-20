from typing import Literal

from pgvector import Vector

from .config import Settings
from .db import connect
from .schemas import Candidate


def find_matches(
    settings: Settings, target_type: Literal["FOUND", "LOST"], embedding: list[float]
) -> list[Candidate]:
    sql = """
        SELECT p.id, 1 - (e.embedding <=> %(query)s::vector) AS score
          FROM post_embeddings AS e
          JOIN posts AS p ON p.id = e.post_id
         WHERE p.post_type = %(target)s AND p.status = 'OPEN'
         ORDER BY e.embedding <=> %(query)s::vector, p.id
         LIMIT 20
    """
    with connect(settings) as connection:
        rows = connection.execute(
            sql, {"query": Vector(embedding).to_text(), "target": target_type}
        ).fetchall()
    return [Candidate(post_id=post_id, score=score) for post_id, score in rows]

