from apps.base.models import BusinessEntity
from pydantic import model_validator
from pymongo import ASCENDING, IndexModel
from server.config import Settings


class Application(BusinessEntity):
    name: str
    domain: str

    class Settings:
        indexes = [
            IndexModel([("name", ASCENDING)], unique=True),
            IndexModel([("domain", ASCENDING)], unique=True),
        ]

    @classmethod
    async def get_by_origin(cls, origin: str):
        return await cls.find_one(cls.domain == origin)

    @model_validator(mode="before")
    def validate_domain(data: dict):
        app_name_domain = f"{data.get('name')}.{Settings.root_url}"
        if not data.get("domain"):
            data["domain"] = app_name_domain

        return data
