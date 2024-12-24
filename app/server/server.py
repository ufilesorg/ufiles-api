import logging
from contextlib import asynccontextmanager

import fastapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mongo_base.core import db, exceptions
from fastapi_mongo_base.routes import copy_router
from usso.fastapi.integration import EXCEPTION_HANDLERS as USSO_EXCEPTION_HANDLERS

from . import config


@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):  # type: ignore
    """Initialize application services."""
    await db.init_mongo_db()
    config.Settings.config_logger()

    logging.info("Startup complete")
    yield
    logging.info("Shutdown complete")


app = fastapi.FastAPI(
    title="Ufiles",
    # description=DESCRIPTION,
    version="0.1.0",
    contact={
        "name": "Mahdi Kiani",
        "url": "https://github.com/ufilesorg/ufiles-api",
        "email": "mahdikiany@gmail.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://github.com/ufilesorg/ufiles-api/blob/main/LICENSE",
    },
    lifespan=lifespan,
)


for exc_class, handler in (
    exceptions.EXCEPTION_HANDLERS | USSO_EXCEPTION_HANDLERS
).items():
    app.exception_handler(exc_class)(handler)


origins = [
    "http://localhost:8000",
    "http://localhost:3000",
    "https://cmp.liara.run",
    "https://app.pixiee.io",
    "https://stg.pixiee.io",
    "https://cmp-dev.liara.run",
    "https://pixiee.bot.inbeet.tech",
    "https://picsee.bot.inbeet.tech",
    "https://dashboard.pixiee.bot.inbeet.tech",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from apps.applications.routes import router as app_router
from apps.business.routes import router as business_router
from apps.files.routes import download_router
from apps.files.routes import router as files_router
from apps.s3.routes import router as s3_router

app.include_router(files_router, prefix="/v1")
app.include_router(
    copy_router(files_router, new_prefix="/files"), include_in_schema=False
)
app.include_router(download_router, prefix="/v1")
app.include_router(business_router, prefix="/v1")
app.include_router(app_router, prefix="/v1")
app.include_router(s3_router)


@app.get("/health")
async def health():
    return {"status": "UP"}
