from typing import Any, Generic, Type, TypeVar

import singleton
from core.exceptions import BaseHTTPException
from fastapi import APIRouter, BackgroundTasks, Query, Request
from server.config import Settings

from .handlers import create_dto, update_dto
from .models import BaseEntity, BaseEntityTaskMixin
from .schemas import PaginatedResponse

# Define a type variable
T = TypeVar("T", bound=BaseEntity)
TE = TypeVar("TE", bound=BaseEntityTaskMixin)


class AbstractBaseRouter(Generic[T], metaclass=singleton.Singleton):
    def __init__(
        self,
        model: Type[T],
        user_dependency: Any,
        *args,
        prefix: str = None,
        tags: list[str] = None,
        **kwargs,
    ):
        self.model = model
        self.user_dependency = user_dependency
        if prefix is None:
            prefix = f"/{self.model.__name__.lower()}s"
        if tags is None:
            tags = [self.model.__name__]
        self.router = APIRouter(prefix=prefix, tags=tags, **kwargs)

        self.config_schemas(**kwargs)
        self.config_routes(**kwargs)

    def config_schemas(self, **kwargs):
        self.list_response_schema = PaginatedResponse[self.model]
        self.retrieve_response_schema = self.model
        self.create_response_schema = self.model
        self.update_response_schema = self.model
        self.delete_response_schema = self.model

        self.create_request_schema = self.model
        self.update_request_schema = self.model

    def config_routes(self, **kwargs):
        self.router.add_api_route(
            "/",
            self.list_items,
            methods=["GET"],
            response_model=self.list_response_schema,
            status_code=200,
        )
        self.router.add_api_route(
            "/{uid:uuid}",
            self.retrieve_item,
            methods=["GET"],
            response_model=self.retrieve_response_schema,
            status_code=200,
        )
        self.router.add_api_route(
            "/",
            self.create_item,
            methods=["POST"],
            response_model=self.create_response_schema,
            status_code=201,
        )
        self.router.add_api_route(
            "/{uid:uuid}",
            self.update_item,
            methods=["PATCH"],
            response_model=self.update_response_schema,
            status_code=200,
        )
        self.router.add_api_route(
            "/{uid:uuid}",
            self.delete_item,
            methods=["DELETE"],
            response_model=self.delete_response_schema,
            # status_code=204,
        )

    async def get_user(self, request: Request, *args, **kwargs):
        if self.user_dependency is None:
            return None
        return await self.user_dependency(request)

    async def list_items(
        self,
        request: Request,
        offset: int = Query(0, ge=0),
        limit: int = Query(10, ge=1, le=Settings.page_max_limit),
    ):
        user = await self.get_user(request)

        items_query = (
            self.model.get_query(user=user)
            .sort("-created_at")
            .skip(offset)
            .limit(limit)
        )
        items = await items_query.to_list()
        total_items = await self.model.get_query(user=user).count()
        return PaginatedResponse(
            items=items,
            total=total_items,
            offset=offset,
            limit=limit,
        )

    async def retrieve_item(
        self,
        request: Request,
        uid,
    ):
        user = await self.get_user(request)
        item = await self.model.get_item(uid, user)
        if item is None:
            raise BaseHTTPException(
                status_code=404,
                error="item_not_found",
                message=f"{self.model.__name__.capitalize()} not found",
            )
        return item

    async def create_item(
        self,
        request: Request,
    ):
        user = await self.get_user(request)
        item = await create_dto(self.model)(request, user)

        await item.save()
        return item

    async def update_item(
        self,
        request: Request,
        uid,
    ):
        user = await self.get_user(request)
        item = await update_dto(self.model)(request, user)
        if item is None:
            raise BaseHTTPException(
                status_code=404,
                error="item_not_found",
                message=f"{self.model.__name__.capitalize()} not found",
            )
        await item.save()
        return item

    async def delete_item(
        self,
        request: Request,
        uid,
    ):
        user = await self.get_user(request)
        item = await self.model.get_item(uid, user)
        if item is None:
            raise BaseHTTPException(
                status_code=404,
                error="item_not_found",
                message=f"{self.model.__name__.capitalize()} not found",
            )
        item.is_deleted = True
        await item.save()
        return item


class AbstractTaskRouter(AbstractBaseRouter[TE]):
    def __init__(self, model: Type[TE], user_dependency: Any, *args, **kwargs):
        super().__init__(model, user_dependency, *args, **kwargs)
        self.router.add_api_route(
            "/{uid:uuid}/start",
            self.start,
            methods=["POST"],
            response_model=self.model,
        )

    async def start(self, request: Request, uid, background_tasks: BackgroundTasks):
        user = await self.get_user(request)
        item = await self.model.get_item(uid, user)
        if item is None:
            raise BaseHTTPException(
                status_code=404,
                error="item_not_found",
                message=f"{self.model.__name__.capitalize()} not found",
            )
        background_tasks.add_task(item.start_processing)
        return item.model_dump()


def copy_router(router: APIRouter, new_prefix: str):
    new_router = APIRouter(prefix=new_prefix)
    for route in router.routes:
        new_router.add_api_route(
            route.path.replace(router.prefix, ""),
            route.endpoint,
            methods=[
                method
                for method in route.methods
                if method in ["GET", "POST", "PUT", "DELETE", "PATCH"]
            ],
            name=route.name,
            response_class=route.response_class,
            status_code=route.status_code,
            tags=route.tags,
            dependencies=route.dependencies,
            summary=route.summary,
            description=route.description,
            response_description=route.response_description,
            responses=route.responses,
            deprecated=route.deprecated,
            include_in_schema=route.include_in_schema,
            response_model=route.response_model,
            response_model_include=route.response_model_include,
            response_model_exclude=route.response_model_exclude,
            response_model_by_alias=route.response_model_by_alias,
        )

    return new_router
