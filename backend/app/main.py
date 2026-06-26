from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import chat
from backend.app.api.routes import documents
from backend.app.api.routes import sessions
import logging

from backend.app.services.document_service import recover_orphaned_documents
from backend.app.services.job_runner import InProcessJobRunner

logger = logging.getLogger(__name__)
runner = InProcessJobRunner()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    try:
        recover_orphaned_documents()
    except Exception:
        logger.exception("Failed to recover orphaned documents on startup")
    try:
        runner.recover_interrupted_jobs()
    except Exception:
        logger.exception("Failed to recover interrupted jobs on startup")
    try:
        runner.start()
        yield
    finally:
        runner.stop()


app = FastAPI(title="SciPal API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "job_runner": runner.health_status() if runner is not None else {},
    }
