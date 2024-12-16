from beanie import init_beanie
from fastapi_mongo_base.models import BaseEntity
from motor.motor_asyncio import AsyncIOMotorClient

from utils.basic import get_all_subclasses

from .config import Settings


async def init_db():
    client = AsyncIOMotorClient(Settings.mongo_uri)
    db = client.get_database(Settings.project_name)
    await init_beanie(database=db, document_models=get_all_subclasses(BaseEntity))
    return db
