import uuid
from datetime import datetime

from apps.base.schemas import PaginatedResponse
from apps.business.handlers import create_dto_business
from apps.business.middlewares import get_business
from apps.business.models import Business
from apps.business.routes import AbstractBusinessBaseRouter
from apps.files.models import FileMetaData
from apps.files.services import generate_presigned_url, process_file, stream_from_s3
from core.exceptions import BaseHTTPException
from fastapi import APIRouter, Body, Depends, File, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from server.config import Settings
from usso import UserData
from usso.exceptions import USSOException
from usso.fastapi import jwt_access_security
from utils import aionetwork

from .schemas import FileMetaDataOut, FileMetaDataUpdate, MultiPartOut, PartUploadOut


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
            response_model=PaginatedResponse[FileMetaDataOut],
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
            self.delete_item,
            methods=["DELETE"],
            response_model=FileMetaDataOut,
        )

    async def list_items(
        self,
        request: Request,
        business: Business = Depends(get_business),
        user_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 50,
        parent_id: uuid.UUID | None = None,
        filename: str | None = None,
        filehash: str | None = None,
        is_deleted: bool = False,
        is_directory: bool | None = None,
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
    ):
        file: FileMetaData = await self.get_file(request, uid, business)

        if file.is_directory:
            return await self.list_items(
                request=request,
                offset=0,
                limit=Settings.page_max_limit,
                business=business,
                parent_id=file.uid,
            )

        if details:
            return FileMetaDataOut(**file.model_dump(), url=file.url)

        file.access_at = datetime.now()
        await file.save()

        if stream:
            return StreamingResponse(
                stream_from_s3(file.s3_key, config=business.config),
                media_type=file.content_type,
                headers={"Content-Disposition": f"inline; filename={file.filename}"},
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
        user: UserData = await self.get_user(request)
        item: FileMetaData = await create_dto_business(self.model)(
            request, user, root_url=business.root_url
        )

        await item.save()
        return item

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

        new_item: FileMetaData = item.model_copy(
            update=update.model_dump(exclude_unset=True, exclude=["permissions"])
        )
        new_item.public_permission.created_at = item.public_permission.created_at
        for permission in update.permissions:
            new_item.set_permission(permission)

        await new_item.save()
        return new_item

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
    user: UserData = Depends(jwt_access_security),
    business: Business = Depends(get_business),
    user_id: uuid.UUID | None = Body(default=None),
    blocking: bool = False,
    file: UploadFile = File(...),
    parent_id: uuid.UUID | None = Body(default=None),
    filename: str | None = Body(default=None),
):
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
    user: UserData = Depends(jwt_access_security),
    business: Business = Depends(get_business),
    user_id: uuid.UUID | None = Body(default=None),
    blocking: bool = False,
    parent_id: uuid.UUID | None = Body(default=None),
    filename: str | None = Body(default=None),
):
    if user is None:
        raise USSOException(status_code=401, error="unauthorized")

    file = await aionetwork.aio_request_binary(url=url)
    upload_file = UploadFile(file=file, filename=filename or url.split("/")[-1])
    return await upload_file(
        request, user, business, user_id, blocking, upload_file, parent_id, filename
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


download_router = APIRouter(
    prefix="/d",
    tags=["files"],
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

    if stream:
        return StreamingResponse(
            stream_from_s3(file.s3_key, config=business.config),
            media_type=file.content_type,
            headers={"Content-Disposition": f"attachment; filename={file.filename}"},
        )

    presigned_url = await generate_presigned_url(file.s3_key, config=business.config)

    return RedirectResponse(presigned_url)
