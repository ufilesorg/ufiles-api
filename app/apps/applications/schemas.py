from fastapi_mongo_base.schemas import BusinessEntitySchema


class ApplicationSchema(BusinessEntitySchema):
    name: str
    domain: str
