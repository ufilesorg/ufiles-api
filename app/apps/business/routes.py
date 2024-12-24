from typing import TypeVar

from fastapi_mongo_base.models import BusinessEntity
from fastapi_mongo_base.routes import AbstractBaseRouter
from fastapi_mongo_base.schemas import BaseEntitySchema
from usso.fastapi import jwt_access_security

from .models import Business
from .schemas import BusinessSchema

T = TypeVar("T", bound=BusinessEntity)
TS = TypeVar("TS", bound=BaseEntitySchema)


class BusinessRouter(AbstractBaseRouter[Business, BusinessSchema]):
    def __init__(self):
        super().__init__(
            model=Business,
            schema=BusinessSchema,
            user_dependency=jwt_access_security,
            prefix="/businesses",
        )

    def config_routesa(self, **kwargs):
        self.router.add_api_route(
            "/",
            self.list_items,
            methods=["GET"],
            response_model=self.list_response_schema,
            status_code=200,
        )
        # self.router.add_api_route(
        #     "/{uid:uuid}",
        #     self.retrieve_item,
        #     methods=["GET"],
        #     response_model=self.retrieve_response_schema,
        #     status_code=200,
        # )
        # self.router.add_api_route(
        #     "/",
        #     self.create_item,
        #     methods=["POST"],
        #     response_model=self.create_response_schema,
        #     status_code=201,
        # )
        # self.router.add_api_route(
        #     "/{uid:uuid}",
        #     self.update_item,
        #     methods=["PATCH"],
        #     response_model=self.update_response_schema,
        #     status_code=200,
        # )
        # self.router.add_api_route(
        #     "/{uid:uuid}",
        #     self.delete_item,
        #     methods=["DELETE"],
        #     response_model=self.delete_response_schema,
        #     # status_code=204,
        # )


router = BusinessRouter().router
