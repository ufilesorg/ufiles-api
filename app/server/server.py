from apps.applications.routes import router as app_router
from apps.business.routes import router as business_router
from apps.files.routes import download_router
from apps.files.routes import router as files_router

# from apps.s3.routes import router as s3_router
from fastapi_mongo_base.core import app_factory
from fastapi_mongo_base.routes import copy_router

from . import config

app = app_factory.create_app(
    settings=config.Settings(),
    origins=[
        "http://localhost:8000",
        "http://localhost:3000",
        "https://pixiee.io",
        "https://pixy.ir",
        "https://studio.pixy.ir",
        "https://studio.pixiee.io",
        "https://dev.pixy.ir",
        "capacitor://localhost",
        "http://localhost",
        "https://localhost",
    ],
)
app.include_router(files_router, prefix="/v1")
app.include_router(
    copy_router(files_router, new_prefix="/files"), include_in_schema=False
)
app.include_router(download_router, prefix="/v1")
app.include_router(business_router, prefix="/v1")
app.include_router(app_router, prefix="/v1")
app.include_router(app_router, prefix="/api/v1", include_in_schema=False)


# app.include_router(s3_router, include_in_schema=False)
