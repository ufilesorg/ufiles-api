from typing import TypeVar

from apps.base.models import BusinessEntity
from apps.base.routes import AbstractBaseRouter
from apps.base.schemas import PaginatedResponse
from apps.business.handlers import create_dto_business, update_dto_business
from core.exceptions import BaseHTTPException
from fastapi import Depends, Request
from server.config import Settings
from usso.fastapi import jwt_access_security

from .middlewares import get_business
from .models import Business

T = TypeVar("T", bound=BusinessEntity)


class AbstractBusinessBaseRouter(AbstractBaseRouter[T]):
    async def list_items(
        self,
        request: Request,
        offset: int = 0,
        limit: int = 10,
        business: Business = Depends(get_business),
    ):
        user = await self.get_user(request)
        limit = max(1, min(limit, Settings.page_max_limit))

        items_query = (
            self.model.get_query(business_name=business.name, user_id=user.uid)
            .sort("-created_at")
            .skip(offset)
            .limit(limit)
        )
        items = await items_query.to_list()
        total_items = await self.model.get_query(
            business_name=business.name, user=user
        ).count()
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
        business: Business = Depends(get_business),
    ):
        user = await self.get_user(request)
        item = await self.model.get_item(
            uid, business_name=business.name, user_id=user.uid
        )
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
        # business: Business = Depends(get_business),
    ):
        user = await self.get_user(request)
        item = await create_dto_business(self.model)(request, user)

        await item.save()
        return item

    async def update_item(
        self,
        request: Request,
        uid,
        # business: Business = Depends(get_business),
    ):
        user = await self.get_user(request)
        item = await update_dto_business(self.model)(request, user)
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
        business: Business = Depends(get_business),
    ):
        user = await self.get_user(request)
        item = await self.model.get_item(
            uid, business_name=business.name, user_id=user.uid
        )
        if item is None:
            raise BaseHTTPException(
                status_code=404,
                error="item_not_found",
                message=f"{self.model.__name__.capitalize()} not found",
            )
        item.is_deleted = True
        await item.save()
        return item


class BusinessRouter(AbstractBaseRouter[Business]):
    def __init__(self):
        super().__init__(
            model=Business,
            user_dependency=jwt_access_security,
            prefix="/businesses",
        )


router = BusinessRouter().router
