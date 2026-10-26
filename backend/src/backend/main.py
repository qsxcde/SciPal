"""Application assembly: settings, routers, error mapping and the job worker."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.errors import register_exception_handlers
from backend.api.routes import auth, chat, documents, sessions
from backend.application.documents import recover_orphaned_documents
from backend.config import env_file_path, repo_env_file_warning, settings
from backend.storage.sqlite.schema import init_db
from backend.worker.handlers import register_default_handlers
from backend.worker.runner import InProcessJobRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)
runner = InProcessJobRunner()


def _log_configuration_source() -> None:
    """Make the effective .env path visible; a stray root-level .env is ignored."""
    env_path = env_file_path()
    if env_path.is_file():
        logger.info("Configuration: loading %s", env_path)
    else:
        logger.info("Configuration: %s not found, using environment and defaults", env_path)
    warning = repo_env_file_warning()
    if warning:
        logger.warning(warning)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _log_configuration_source()
    await asyncio.to_thread(init_db)
    try:
        await asyncio.to_thread(recover_orphaned_documents)
    except Exception:
        logger.exception("Failed to recover orphaned documents on startup")
    try:
        await asyncio.to_thread(runner.recover_interrupted_jobs)
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
    allow_origin_regex=settings.cors_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
register_default_handlers()

app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "job_runner": runner.health_status() if runner is not None else {},
    }


def main() -> None:
    """Entry point for the ``scipal-backend`` console script."""
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000)
