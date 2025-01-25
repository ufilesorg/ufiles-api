import re
import uuid
from datetime import datetime
from typing import Literal
from urllib.parse import quote

from apps.business.middlewares import get_business
from apps.business.models import Business
from fastapi import APIRouter, Body, Depends, File, Request, UploadFile
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from fastapi_mongo_base.core.exceptions import BaseHTTPException
from fastapi_mongo_base.schemas import PaginatedResponse
from fastapi_mongo_base.utils import aionetwork, imagetools
from server.config import Settings

# from apps.business.routes import AbstractBusinessBaseRouter
from ufaas_fastapi_business.routes import AbstractBusinessBaseRouter
from usso import UserData
from usso.exceptions import USSOException
from usso.fastapi import jwt_access_security

from .models import FileMetaData
from .schemas import (
    FileMetaDataCreate,
    FileMetaDataOut,
    FileMetaDataUpdate,
    MultiPartOut,
    PartUploadOut,
)
from .services import (
    change_file,
    convert_image_from_s3,
    download_from_s3,
    generate_presigned_url,
    process_file,
    stream_from_s3,
)


class FilesRouter(AbstractBusinessBaseRouter[FileMetaData, FileMetaDataOut]):
    def __init__(self):
        super().__init__(
            model=FileMetaData,
            schema=FileMetaDataOut,
            user_dependency=jwt_access_security,
            prefix="/f",
            tags=["files"],
        )

    def config_routes(self):
        self.router.add_api_route(
            "/",
            self.list_items,
            methods=["GET"],
            response_model=PaginatedResponse[FileMetaDataOut],
        )
        self.router.add_api_route(
            "/volume",
            self.get_volume,
            methods=["GET"],
            # response_model=VolumeOut,
        )
        self.router.add_api_route(
            "/{uid:uuid}",
            self.retrieve_item,
            methods=["GET"],
            # response_model=FileMetaDataSignedUrl,
        )
        self.router.add_api_route(
            "/{uid:uuid}/{path:path}",
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
            self.change_item,
            methods=["PUT"],
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
        business: Business = Depends(get_business),
        offset: int = 0,
        limit: int = 50,
        parent_id: uuid.UUID | None = None,
        filename: str | None = None,
        filehash: str | None = None,
        is_deleted: bool = False,
        is_directory: bool | None = None,
        user_id: uuid.UUID | None = None,
        content_type: str | None = None,
    ):
        try:
            user: UserData = await self.get_user(request)
        except USSOException as e:
            if parent_id is None:
                raise e
            user = None

        if not user:
            user_id = None
        elif user and user.uid != business.user_id:
            user_id = user.uid
        elif user_id is None:
            user_id = user.uid

        params = dict(request.query_params)
        params.pop("user_id", None)
        params.pop("root_permission", None)
        params.pop("offset", None)
        params.pop("limit", None)
        params.pop("parent_id", None)
        params.pop("filename", None)
        params.pop("filehash", None)
        params.pop("is_deleted", None)
        params.pop("is_directory", None)

        limit = max(1, min(limit, Settings.page_max_limit))

        items, total_items = await FileMetaData.list_files(
            user_id,
            business.name,
            offset,
            limit,
            parent_id=parent_id,
            filename=filename,
            filehash=filehash,
            is_deleted=is_deleted,
            is_directory=is_directory,
            **params,
        )
        return PaginatedResponse(
            items=items, offset=offset, limit=limit, total=total_items
        )

    async def get_volume(
        self,
        request: Request,
        business: Business = Depends(get_business),
    ):
        user: UserData = await self.get_user(request)
        volume = await FileMetaData.get_volume(user.uid, business.name)
        return {"volume": volume}

    async def get_file(
        self,
        request: Request,
        uid: uuid.UUID,
        business: Business = Depends(get_business),
        user_id: uuid.UUID | None = None,
    ):
        try:
            user: UserData = await self.get_user(request)
        except USSOException:
            user = None

        root_permission = bool(user and user.uid == business.user_id)

        if not user:
            user_id = None
        elif user and user.uid != business.user_id:
            user_id = user.uid

        file = await FileMetaData.get_file(
            user_id=user_id,
            business_name=business.name,
            file_id=uid,
            root_permission=root_permission,
        )

        if file is None:
            raise BaseHTTPException(
                status_code=404, error="file_not_found", message="File not found"
            )

        if not file.user_permission(user.uid if user else None).read:
            raise BaseHTTPException(
                status_code=404, error="file_not_found", message="File not found"
            )

        return file

    async def retrieve_item(
        self,
        request: Request,
        uid: uuid.UUID,
        business: Business = Depends(get_business),
        stream: bool = True,
        details: bool = False,
        convert_format: Literal["png", "jpeg", "webp"] = None,
        width: int | None = None,
        height: int | None = None,
    ):
        file: FileMetaData = await self.get_file(request, uid, business)

        if details:
            return FileMetaDataOut(**file.model_dump(), url=file.url)

        if file.is_directory:
            return await self.list_items(
                request=request,
                offset=0,
                limit=Settings.page_max_limit,
                business=business,
                parent_id=file.uid,
            )

        file.access_at = datetime.now()
        await file.save()

        if width or height:
            if file.content_type.startswith("image"):
                image_bytes = await download_from_s3(
                    file.s3_key, config=business.config
                )
                resized_image = imagetools.resize_image(image_bytes, width, height)
                result_image = imagetools.convert_image_bytes(
                    resized_image, convert_format if convert_format else "jpeg"
                )
                return StreamingResponse(
                    result_image,
                    media_type=(
                        "image/jpeg"
                        if convert_format is None
                        else f"image/{convert_format}"
                    ),
                    headers={
                        "Content-Disposition": f"inline; filename*=UTF-8''{quote(file.filename)}",
                        "Content-length": str(len(result_image.getbuffer())),
                        # "Content-type": (
                        #     "image/webp"
                        #     if convert_format is None
                        #     else f"image/{convert_format}"
                        # ),
                    },
                )

        if convert_format:
            if file.content_type.startswith("image"):
                file_byte = await convert_image_from_s3(
                    file.s3_key, config=business.config, format=convert_format
                )
                ext = convert_format.lower()
                filename = f"{file.filename.rsplit('.', 1)[0]}.{ext}"
                return StreamingResponse(
                    file_byte,
                    media_type=file.content_type,
                    headers={
                        "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
                        "Content-length": str(len(file_byte.getbuffer())),
                        "Content-type": f"image/{convert_format}",
                    },
                )
            raise NotImplementedError("Convert is not implemented yet")

        if stream:
            range_header = request.headers.get("Range")
            file_size = file.size

            if range_header:
                # Parse the Range header (e.g., "bytes=0-1023")
                range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
                if not range_match:
                    raise BaseHTTPException(
                        status_code=400, detail="Invalid Range header"
                    )

                start = int(range_match.group(1))
                end = (
                    int(range_match.group(2)) if range_match.group(2) else file_size - 1
                )

                if start >= file_size or end >= file_size:
                    return Response(
                        status_code=416,
                        headers={"Content-Range": f"bytes */{file_size}"},
                    )

                chunk_size = end - start + 1
                stream = stream_from_s3(
                    file.s3_key, config=business.config, start=start, end=end
                )

                headers = {
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(chunk_size),
                    "Content-Disposition": f"inline; filename*=UTF-8''{quote(file.filename)}",
                    "Content-Type": file.content_type,
                }

                return StreamingResponse(stream, status_code=206, headers=headers)

            # Full file streaming
            return StreamingResponse(
                stream_from_s3(file.s3_key, config=business.config),
                media_type=file.content_type,
                headers={
                    "Content-Disposition": f"inline; filename*=UTF-8''{quote(file.filename)}",
                    "Content-length": str(file.size),
                    "Accept-Ranges": "bytes",
                },
            )

        presigned_url = await generate_presigned_url(
            file.s3_key, config=business.config
        )

        return RedirectResponse(presigned_url)

    async def create_item(
        self,
        request: Request,
        data: FileMetaDataCreate,
        business: Business = Depends(get_business),
    ):
        user_id = await self.get_user_id(request)
        item = FileMetaData(
            user_id=user_id,
            business_name=business.name,
            access_at=datetime.now(),
            **data.model_dump(exclude_none=True, exclude_unset=True),
        )
        await item.save()
        return item

    async def change_item(
        self,
        request: Request,
        uid: uuid.UUID,
        blocking: bool = False,
        file: UploadFile = File(...),
        overwrite: bool = False,
        business: Business = Depends(get_business),
    ):
        user: UserData = await self.get_user(request)
        item: FileMetaData = await self.get_file(request, uid, business)

        if not item.user_permission(user.uid).write:
            raise BaseHTTPException(
                status_code=403,
                error="forbidden",
                message="You don't have permission to update this file",
            )

        if item.is_deleted:
            raise BaseHTTPException(
                status_code=400,
                error="file_deleted",
                message="File is deleted",
            )

        meta_data = await change_file(
            file=file, file_metadata=item, blocking=blocking, overwrite=overwrite
        )
        return meta_data

    async def update_item(
        self,
        request: Request,
        uid,
        update: FileMetaDataUpdate,
        business: Business = Depends(get_business),
    ):
        user: UserData = await self.get_user(request)
        item: FileMetaData = await self.get_file(request, uid, business)

        if not item.user_permission(user.uid).write:
            raise BaseHTTPException(
                status_code=403,
                error="forbidden",
                message="You don't have permission to update this file",
            )

        if update.need_manage_permissions and not item.user_permission(user.uid).manage:
            raise BaseHTTPException(
                status_code=403,
                error="forbidden",
                message="You don't have permission to manage permissions",
            )

        if update.is_deleted is not None:
            if item.is_deleted and not update.is_deleted:
                await item.restore(user.uid)
            elif not item.is_deleted and update.is_deleted:
                await item.delete(user.uid)
        if update.filename:
            item.filename = update.filename
        if update.parent_id:
            existing, _ = await FileMetaData.list_files(
                user_id=user.uid,
                business_name=business.name,
                file_id=update.parent_id,
            )
            if not existing or not existing[0].is_directory:
                raise BaseHTTPException(
                    status_code=404,
                    error="parent_not_found",
                    message="Parent directory not found",
                )
            item.parent_id = update.parent_id
        if update.public_permission:
            item.public_permission.permission = update.public_permission.permission
            item.public_permission.updated_at = datetime.now()
        for permission in update.permissions:
            await item.set_permission(permission)

        await item.save()
        return item

    async def delete_item(
        self,
        request: Request,
        uid: uuid.UUID,
        business: Business = Depends(get_business),
    ):
        user: UserData = await self.get_user(request)
        file: FileMetaData = await self.get_file(request, uid, business)

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

        await file.delete(user_id=user.uid)
        return file


router = FilesRouter().router


@router.post("/upload", response_model=FileMetaDataOut)
async def upload_file(
    request: Request,
    # user: UserData = Depends(jwt_access_security),
    # business: Business = Depends(get_business),
    user_id: uuid.UUID | None = Body(default=None),
    blocking: bool = False,
    file: UploadFile = File(...),
    parent_id: uuid.UUID | None = Body(default=None),
    filename: str | None = Body(default=None),
):
    user: UserData = jwt_access_security(request)
    business: Business = await get_business(request)

    if user is None:
        raise USSOException(status_code=401, error="unauthorized")

    if user.uid != business.user_id:
        user_id = user.uid
    elif user_id is None:
        user_id = user.uid

    form_data = dict(await request.form())
    form_data.pop("user_id", None)
    form_data.pop("parent_id", None)
    form_data.pop("filename", None)
    file = form_data.pop("file", file)

    file_metadata = await process_file(
        file=file,
        user_id=user_id,
        business=business,
        blocking=blocking,
        parent_id=parent_id,
        filename=filename,
        **form_data,
    )
    await file_metadata.save()

    return file_metadata


@router.post("/url", response_model=FileMetaDataOut)
async def upload_url(
    request: Request,
    url: str = Body(),
    user_id: uuid.UUID | None = Body(default=None),
    blocking: bool = False,
    parent_id: uuid.UUID | None = Body(default=None),
    filename: str | None = Body(default=None),
):
    user: UserData = jwt_access_security(request)
    business: Business = await get_business(request)

    if user is None:
        raise USSOException(status_code=401, error="unauthorized")

    file = await aionetwork.aio_request_binary(url=url)
    uploading_file = UploadFile(file=file, filename=filename or url.split("/")[-1])
    return await upload_file(
        request, user_id, blocking, uploading_file, parent_id, filename
    )


@router.post("/multipart", response_model=MultiPartOut, include_in_schema=False)
async def start_multipart(
    user=Depends(jwt_access_security),
    business: Business = Depends(get_business),
    parent_id: uuid.UUID | None = Body(default=None),
    filename: str | None = Body(default=None),
    filehash: str = Body(),
):
    if user is None:
        raise USSOException(status_code=401, error="unauthorized")

    raise NotImplementedError("Multipart upload is not implemented yet")

    return file_metadata


@router.post(
    "/multipart/{upload_id:str}", response_model=PartUploadOut, include_in_schema=False
)
async def upload_part(
    upload_id: str,
    part: UploadFile = File(...),
    user=Depends(jwt_access_security),
    business: Business = Depends(get_business),
    part_number: int = Body(),
    blocking: bool = False,
):
    if user is None:
        raise USSOException(status_code=401, error="unauthorized")

    raise NotImplementedError("Multipart upload is not implemented yet")

    return file_metadata


@router.post(
    "/multipart/{upload_id:str}/complete",
    response_model=FileMetaDataOut,
    include_in_schema=False,
)
async def finish_multipart(
    upload_id: str,
    user=Depends(jwt_access_security),
    business: Business = Depends(get_business),
):
    if user is None:
        raise USSOException(status_code=401, error="unauthorized")

    raise NotImplementedError("Multipart upload is not implemented yet")

    return file_metadata


download_router = APIRouter(prefix="/d", tags=["files"])


@download_router.get(
    "/{uid:uuid}/{path:path}",
    include_in_schema=False,
    # response_class=RedirectResponse | StreamingResponse,
)
@download_router.get(
    "/{uid:uuid}",
    include_in_schema=False,
    # response_class=RedirectResponse | StreamingResponse,
)
async def download_file_endpoint(
    request: Request,
    uid: uuid.UUID,
    business: Business = Depends(get_business),
    stream: bool = True,
    convert_format: Literal["png", "jpeg", "webp"] = None,
):
    file = await FilesRouter().get_file(request, uid, business)

    if file.is_directory:
        raise BaseHTTPException(
            status_code=400,
            error="directory_is_not_downloadable",
            message="Directory is not downloadable",
        )

    file.access_at = datetime.now()
    await file.save()

    if convert_format:
        if file.content_type.startswith("image"):
            file_byte = await convert_image_from_s3(
                file.s3_key, config=business.config, format=convert_format
            )
            ext = convert_format.lower()
            filename = f"{file.filename.rsplit('.', 1)[0]}.{ext}"
            return StreamingResponse(
                file_byte,
                media_type=file.content_type,
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
                    "Content-length": str(len(file_byte.getbuffer())),
                },
            )
        raise NotImplementedError("Convert is not implemented yet")

    if stream:
        return StreamingResponse(
            stream_from_s3(file.s3_key, config=business.config),
            media_type=file.content_type,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file.filename)}",
                "Content-length": str(file.size),
            },
        )

    presigned_url = await generate_presigned_url(file.s3_key, config=business.config)

    return RedirectResponse(presigned_url)
