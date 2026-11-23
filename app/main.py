import logging
from asyncio import sleep
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings
from .embeddings import Encoder
from .routes import router


logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = Settings()
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            app.state.encoder = Encoder()
            break
        except Exception:
            if attempt == max_attempts:
                logger.exception("SigLIP2 initialization failed (%d/%d), aborting startup", attempt, max_attempts)
                raise
            logger.warning("SigLIP2 initialization failed (%d/%d), retrying in 2 seconds", attempt, max_attempts)
            await sleep(2)
    yield
    app.state.encoder = None


app = FastAPI(title="GDGoC 분실물 매칭 AI", lifespan=lifespan)
app.include_router(router)


@app.exception_handler(psycopg.OperationalError)
async def database_unavailable(request: Request, exc: Exception):
    logger.error("PostgreSQL unavailable (%s)", type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "AI service temporarily unavailable"})


@app.exception_handler(Exception)
async def processing_error(request: Request, exc: Exception):
    logger.exception("Request failed at %s", request.url.path)
    detail = "Embedding generation failed" if request.url.path.startswith("/ai/embed/") else "Matching failed"
    return JSONResponse(status_code=500, content={"detail": detail})

