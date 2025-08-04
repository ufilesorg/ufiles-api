import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi_mongo_base.core import app_factory

from apps.files.routes import router as files_router

from . import config, db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Initialize application services."""
    await db.init_mongo_db()
    logging.info("Startup complete")
    yield
    logging.info("Shutdown complete")


app = app_factory.create_app(
    settings=config.Settings(),
    lifespan_func=lifespan,
)


server_router = APIRouter()

for router in [files_router]:
    server_router.include_router(router)

app.include_router(server_router, prefix=config.Settings.base_path)
