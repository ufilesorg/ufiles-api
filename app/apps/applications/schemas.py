from fastapi_mongo_base.schemas import BusinessEntitySchema


class ApplicationSchema(BusinessEntitySchema):
    name: str
    domain: str
    description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
