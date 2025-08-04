import asyncio
import logging

from beanie import init_beanie
from fastapi_mongo_base.models import BaseEntity
from fastapi_mongo_base.utils import basic

from .config import Settings


async def init_mongo_db(settings: Settings | None = None) -> object:
    from mongomock_motor import AsyncMongoMockClient

    if settings is None:
        settings = Settings()

    client = AsyncMongoMockClient()

    try:
        await client.server_info()
    except Exception:
        logging.exception("Error initializing MongoDB")
        raise
    except asyncio.CancelledError:
        logging.exception("Initializing MongoDB cancelled")
        raise

    database = client.get_database(settings.project_name)
    await init_beanie(
        database=database,
        document_models=[
            cls
            for cls in basic.get_all_subclasses(BaseEntity)
            if not (
                "Settings" in cls.__dict__
                and getattr(cls.Settings, "__abstract__", False)
            )
        ],
    )
    return database
