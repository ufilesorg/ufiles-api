import uuid
from datetime import datetime

from beanie import Document, Insert, Replace, before_event

from .schemas import (
    BaseEntitySchema,
    BusinessEntitySchema,
    BusinessOwnedEntitySchema,
    OwnedEntitySchema,
)


class BaseEntity(BaseEntitySchema, Document):
    class Settings:
        keep_nulls = False
        validate_on_save = True

    @before_event([Insert, Replace])
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
    def get_query(cls, business_id: uuid.UUID, *args, **kwargs):
        query = cls.find(cls.is_deleted == False, cls.business_id == business_id)
        return query

    @classmethod
    async def get_item(cls, uid, business_id, *args, **kwargs) -> "BusinessEntity":
        query = cls.get_query(business_id, *args, **kwargs).find(cls.uid == uid)
        items = await query.to_list()
        if not items:
            return None
        return items[0]


class BusinessOwnedEntity(BusinessOwnedEntitySchema, BaseEntity):

    @classmethod
    def get_query(cls, business_id, user_id, *args, **kwargs):
        query = cls.find(
            cls.is_deleted == False,
            cls.business_id == business_id,
            cls.user_id == user_id,
        )
        return query

    @classmethod
    async def get_item(
        cls, uid, business_id, user_id, *args, **kwargs
    ) -> "BusinessOwnedEntity":
        query = cls.get_query(business_id, user_id, *args, **kwargs).find(
            cls.uid == uid
        )
        items = await query.to_list()
        if not items:
            return None
        return items[0]
