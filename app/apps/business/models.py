from fastapi_mongo_base.models import OwnedEntity
from pydantic import model_validator
from pymongo import ASCENDING, IndexModel
from server.config import Settings

from .schemas import BusinessSchema


class Business(BusinessSchema, OwnedEntity):

    class Settings:
        indexes = OwnedEntity.Settings.indexes + [
            IndexModel([("name", ASCENDING)], unique=True),
            IndexModel([("domain", ASCENDING)], unique=True),
        ]

    @property
    def root_url(self):
        if self.domain.startswith("http"):
            return self.domain
        return f"https://{self.domain}"

    @classmethod
    async def get_by_origin(cls, origin: str):
        return await cls.find_one(cls.domain == origin)

    @classmethod
    async def get_by_name(cls, name: str):
        return await cls.find_one(cls.name == name)

    @model_validator(mode="before")
    def validate_domain(data: dict):
        if not data.get("domain"):
            business_name_domain = f"{data.get('name')}.{Settings.root_url}"
            data["domain"] = business_name_domain

        return data
