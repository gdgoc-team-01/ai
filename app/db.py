import psycopg
from fastapi import HTTPException

from .config import Settings


def connect(settings: Settings):
    if settings.database_url is None:
        raise HTTPException(503, "AI service temporarily unavailable")
    return psycopg.connect(settings.database_url.get_secret_value(), connect_timeout=5)

