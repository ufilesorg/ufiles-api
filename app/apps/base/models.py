import uuid
from datetime import datetime

from beanie import Document, Insert, Replace, Save, SaveChanges, Update, before_event
from pymongo import ASCENDING, IndexModel

from .schemas import (
    BaseEntitySchema,
    BusinessEntitySchema,
    BusinessOwnedEntitySchema,
    OwnedEntitySchema,
)
from .tasks import TaskMixin


class BaseEntity(BaseEntitySchema, Document):
    class Settings:
        keep_nulls = False
        validate_on_save = True

        indexes = [
            IndexModel([("uid", ASCENDING)], unique=True),
        ]

    @before_event([Insert, Replace, Save, SaveChanges, Update])
    async def pre_save(self):
        self.updated_at = datetime.now()

    @classmethod
    def get_query(cls, *args, **kwargs):
        query = cls.find(cls.is_deleted == False)
        return query

    @classmethod
    async def get_item(cls, uid, *args, **kwargs) -> "BaseEntity":
        query = cls.get_query(*args, **kwargs).find(cls.uid == uid)
        items = await query.to_list()
        if not items:
            return None
        return items[0]


class OwnedEntity(OwnedEntitySchema, BaseEntity):

    @classmethod
    def get_query(cls, user_id: uuid.UUID, *args, **kwargs):
        query = cls.find(cls.is_deleted == False, cls.user_id == user_id)
        return query

    @classmethod
    async def get_item(cls, uid, user_id, *args, **kwargs) -> "OwnedEntity":
        query = cls.get_query(user_id, *args, **kwargs).find(cls.uid == uid)
        items = await query.to_list()
        if not items:
            return None
        return items[0]


class BusinessEntity(BusinessEntitySchema, BaseEntity):

    @classmethod
    def get_query(cls, business_name: str, *args, **kwargs):
        query = cls.find(cls.is_deleted == False, cls.business_name == business_name)
        return query

    @classmethod
    async def get_item(cls, uid, business_name, *args, **kwargs) -> "BusinessEntity":
        query = cls.get_query(business_name, *args, **kwargs).find(cls.uid == uid)
        items = await query.to_list()
        if not items:
            return None
        return items[0]

    async def get_business(self):
        from apps.business.models import Business

        return await Business.get_by_name(self.business_name)


class BusinessOwnedEntity(BusinessOwnedEntitySchema, BaseEntity):

    @classmethod
    def get_query(cls, business_name, user_id, *args, **kwargs):
        query = cls.find(
            cls.is_deleted == False,
            cls.business_name == business_name,
            cls.user_id == user_id,
        )
        return query

    @classmethod
    async def get_item(
        cls, uid, business_name, user_id, *args, **kwargs
    ) -> "BusinessOwnedEntity":
        query = cls.get_query(business_name, user_id, *args, **kwargs).find(
            cls.uid == uid
        )
        items = await query.to_list()
        if not items:
            return None
        return items[0]


class BaseEntityTaskMixin(BaseEntity, TaskMixin):
    pass
