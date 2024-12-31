import logging
from contextlib import asynccontextmanager

import fastapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mongo_base.core import db, exceptions, app_factory
from fastapi_mongo_base.routes import copy_router
from usso.fastapi.integration import EXCEPTION_HANDLERS as USSO_EXCEPTION_HANDLERS

from . import config


from apps.applications.routes import router as app_router
from apps.business.routes import router as business_router
from apps.files.routes import download_router
from apps.files.routes import router as files_router
from apps.s3.routes import router as s3_router

app = app_factory.create_app(
    origins=[
        "http://localhost:8000",
        "http://localhost:3000",
        "https://cmp.liara.run",
        "https://app.pixiee.io",
        "https://pixiee.io",
        "https://stg.pixiee.io",
        "https://cmp-dev.liara.run",
        "https://pixiee.bot.inbeet.tech",
        "https://picsee.bot.inbeet.tech",
        "https://dashboard.pixiee.bot.inbeet.tech",
        "https://studio.pixy.ir",
    ]
)
app.include_router(files_router, prefix="/v1")
app.include_router(
    copy_router(files_router, new_prefix="/files"), include_in_schema=False
)
app.include_router(download_router, prefix="/v1")
app.include_router(business_router, prefix="/v1")
app.include_router(app_router, prefix="/v1")
app.include_router(s3_router, include_in_schema=False)