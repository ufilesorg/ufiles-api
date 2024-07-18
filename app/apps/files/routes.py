import uuid
from datetime import datetime

from apps.business.handlers import create_dto_business, update_dto_business
from apps.business.middlewares import get_business
from apps.business.models import Business
from apps.business.routes import AbstractBusinessBaseRouter
from apps.files.models import FileMetaData
from apps.files.services import (
    download_from_s3,
    generate_presigned_url,
    get_session,
    save_file_to_s3,
)
from core.exceptions import BaseHTTPException
from fastapi import APIRouter, Body, Depends, File, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from server.config import Settings
from usso import UserData
from usso.exceptions import USSOException
from usso.fastapi import jwt_access_security

from .schemas import FileMetaDataOut


class FilesRouter(AbstractBusinessBaseRouter[FileMetaData]):
    def __init__(self):
        super().__init__(
            model=FileMetaData,
            user_dependency=jwt_access_security,
            prefix="/f",
            tags=["files"],
        )

    def config_routes(self):
        self.router.add_api_route(
            "/",
            self.list_items,
            methods=["GET"],
            response_model=list[FileMetaDataOut],
        )
        self.router.add_api_route(
            "/{uid:uuid}",
            self.retrieve_item,
            methods=["GET"],
            # response_model=FileMetaDataSignedUrl,
        )
        self.router.add_api_route(
            "/",
            self.create_item,
            methods=["POST"],
            response_model=FileMetaDataOut,
            status_code=201,
        )
        self.router.add_api_route(
            "/{uid:uuid}",
            self.update_item,
            methods=["PATCH"],
            response_model=FileMetaDataOut,
        )
        self.router.add_api_route(
            "/{uid:uuid}",
            self.delete_item,
            methods=["DELETE"],
            response_model=FileMetaDataOut,
        )

    async def list_items(
        self,
        request: Request,
        offset: int = 0,
        limit: int = 10,
        business: Business = Depends(get_business),
        user=Depends(jwt_access_security),
        parent_id: uuid.UUID = None,
        filehash: str = None,
    ):
        user: UserData = await self.get_user(request)
        limit = max(limit, Settings.page_max_limit)

        items = await FileMetaData.list_files(
            user.uid,
            business.name,
            offset,
            limit,
            parent_id=parent_id,
            filehash=filehash,
        )
        return items

    async def retrieve_item(
        self,
        uid: uuid.UUID,
        user: UserData = Depends(jwt_access_security),
        business: Business = Depends(get_business),
        stream: bool = True,
    ):
        file = await FileMetaData.get_file(
            user_id=user.uid, business_name=business.name, file_id=uid
        )

        if file is None:
            raise BaseHTTPException(
                status_code=404, error="file_not_found", message="File not found"
            )

        if not file.user_permission(user.uid).read:
            raise BaseHTTPException(
                status_code=404, error="file_not_found", message="File not found"
            )

        if stream:
            session = get_session(business.config)

            async def file_iterator():
                async with session.client(
                    **business.config.s3_client_kwargs
                ) as s3_client:
                    response = await s3_client.get_object(
                        Bucket=business.config.s3_bucket, Key=file.s3_key
                    )

                    async for chunk in response["Body"].iter_chunks():
                        yield chunk

            return StreamingResponse(
                file_iterator(),
                media_type=file.content_type,
                headers={"Content-Disposition": f"inline; filename={file.filename}"},
            )

            file_bytes = await download_from_s3(file.s3_key, config=business.config)
            headers = {"Content-Disposition": f"inline; filename={file.filename}"}

            # return FileResponse(
            #     file_bytes, media_type=file.content_type, filename=file.filename
            # )

            return StreamingResponse(
                file_bytes, media_type=file.content_type, headers=headers
            )

        presigned_url = await generate_presigned_url(
            file.s3_key, config=business.config
        )

        return RedirectResponse(presigned_url)

    async def create_item(
        self,
        request: Request,
        business: Business = Depends(get_business),
    ):
        user = await self.get_user(request)
        item = await create_dto_business(self.model)(
            request, user, root_url=business.root_url
        )

        await item.save()
        return item

    async def update_item(
        self,
        request: Request,
        uid,
        business: Business = Depends(get_business),
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
        uid: uuid.UUID,
        user: UserData = Depends(jwt_access_security),
        business: Business = Depends(get_business),
    ):
        file = await FileMetaData.get_file(
            user_id=user.uid, business_name=business.name, file_id=uid
        )

        if not file:
            raise BaseHTTPException(
                status_code=404, error="file_not_found", message="File not found"
            )

        if not file.user_permission(user.uid).delete:
            if file.user_permission(user.uid).read:
                raise BaseHTTPException(
                    status_code=403,
                    error="forbidden",
                    message="You don't have permission to delete this file",
                )
            else:
                raise BaseHTTPException(
                    status_code=404, error="file_not_found", message="File not found"
                )

        file.is_deleted = True
        file.deleted_at = datetime.now()
        await file.save()
        return file


router = FilesRouter().router


@router.post("/upload", response_model=FileMetaDataOut)
async def upload_file(
    file: UploadFile = File(...),
    user=Depends(jwt_access_security),
    business: Business = Depends(get_business),
    parent_id: uuid.UUID | None = Body(),
    filename: str | None = Body(default=None),
    blocking: bool = False,
):
    if user is None:
        raise USSOException(status_code=401, error="unauthorized")

    file_metadata = await save_file_to_s3(
        file,
        user,
        business,
        parent_id=parent_id,
        filename=filename,
        blocking=blocking,
    )
    await file_metadata.save()

    return file_metadata


download_router = APIRouter(
    prefix="/d",
    tags=["files"],
)


@download_router.get("/{uid:uuid}")
async def stream_file_endpoint(
    uid: uuid.UUID,
    user: UserData = Depends(jwt_access_security),
    business: Business = Depends(get_business),
    stream: bool = True,
):
    file = await FileMetaData.get_file(
        user_id=user.uid, business_name=business.name, file_id=uid
    )

    if file is None:
        raise BaseHTTPException(
            status_code=404, error="file_not_found", message="File not found"
        )

    if not file.user_permission(user.uid).read:
        raise BaseHTTPException(
            status_code=404, error="file_not_found", message="File not found"
        )

    if stream:
        session = get_session(business.config)

        async def file_iterator():
            async with session.client(**business.config.s3_client_kwargs) as s3_client:
                response = await s3_client.get_object(
                    Bucket=business.config.s3_bucket, Key=file.s3_key
                )

                async for chunk in response["Body"].iter_chunks():
                    yield chunk

        return StreamingResponse(
            file_iterator(),
            media_type=file.content_type,
            headers={"Content-Disposition": f"attachment; filename={file.filename}"},
        )

    presigned_url = await generate_presigned_url(file.s3_key, config=business.config)

    return RedirectResponse(presigned_url)
