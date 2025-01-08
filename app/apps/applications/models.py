from fastapi_mongo_base.models import BusinessEntity
from pydantic import model_validator
from pymongo import ASCENDING, TEXT, IndexModel
from server.config import Settings

from .schemas import ApplicationSchema


class Application(ApplicationSchema, BusinessEntity):

    class Settings:
        indexes = BusinessEntity.Settings.indexes + [
            IndexModel(
                [("name", ASCENDING), ("business_name", ASCENDING)], unique=True
            ),
            IndexModel(
                [("domain", ASCENDING), ("business_name", ASCENDING)], unique=True
            ),
            IndexModel(
                [
                    ("name", TEXT),
                    ("description", TEXT),
                    ("category", TEXT),
                    ("tags", TEXT),
                ],  # Text index for search
                name="text_search_index",
            ),
        ]

    @classmethod
    async def search(cls, business_name: str, query: str):
        regex_results = await cls.find(
            {"business_name": business_name, "tags": {"$regex": query, "$options": "i"}}
        ).to_list()
        text_results = await cls.find(
            {"business_name": business_name, "$text": {"$search": query}}
        ).to_list()
        results = {str(result.id): result for result in regex_results + text_results}
        return list(results.values())

    @classmethod
    async def get_by_origin(cls, origin: str):
        return await cls.find_one(cls.domain == origin)

    @model_validator(mode="before")
    def validate_domain(data: dict):
        app_name_domain = f"{data.get('name')}.{Settings.root_url}"
        if not data.get("domain"):
            data["domain"] = app_name_domain

        return data
