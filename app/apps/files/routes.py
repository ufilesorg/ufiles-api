import uuid
from datetime import datetime

from apps.business.handlers import create_dto_business, update_dto_business
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

from .schemas import FileMetaDataOut, MultiPartOut, PartUploadOut


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
        parent_id: uuid.UUID = None,
        filehash: str = None,
        is_deleted: bool = False,
    ):
        try:
            user: UserData = await self.get_user(request)
        except USSOException:
            user = None

        limit = max(1, min(limit, Settings.page_max_limit))

        items = await FileMetaData.list_files(
            user.uid if user else None,
            business.name,
            offset,
            limit,
            parent_id=parent_id,
            filehash=filehash,
            is_deleted=is_deleted,
        )
        return items

    async def get_file(
        self,
        request: Request,
        uid: uuid.UUID,
        business: Business = Depends(get_business),
    ):
        try:
            user: UserData = await self.get_user(request)
        except USSOException:
            user = None

        file = await FileMetaData.get_file(
            user_id=user.uid if user else None, business_name=business.name, file_id=uid
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
    ):
        file = await self.get_file(request, uid, business)

        if file.is_directory:
            return await self.list_items(
                request=request,
                offset=0,
                limit=Settings.page_max_limit,
                business=business,
                parent_id=file.uid,
            )
            return FileMetaDataOut(**file.model_dump())

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
        # todo before change permission
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
    parent_id: uuid.UUID | None = Body(default=None),
    filename: str | None = Body(default=None),
    blocking: bool = False,
):
    if user is None:
        raise USSOException(status_code=401, error="unauthorized")

    file_metadata = await process_file(
        file,
        user,
        business,
        parent_id=parent_id,
        filename=filename,
        blocking=blocking,
    )
    await file_metadata.save()

    return file_metadata


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


@router.post("/url", response_model=FileMetaDataOut)
async def upload_url(
    url: str = Body(),
    user=Depends(jwt_access_security),
    business: Business = Depends(get_business),
    parent_id: uuid.UUID | None = Body(default=None),
    filename: str | None = Body(default=None),
    blocking: bool = False,
):
    if user is None:
        raise USSOException(status_code=401, error="unauthorized")

    file = await aionetwork.aio_request_binary(url=url)
    upload_file = UploadFile(file=file, filename=filename or url.split("/")[-1])

    file_metadata = await process_file(
        upload_file,
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

    if stream:
        return StreamingResponse(
            stream_from_s3(file.s3_key, config=business.config),
            media_type=file.content_type,
            headers={"Content-Disposition": f"attachment; filename={file.filename}"},
        )

    presigned_url = await generate_presigned_url(file.s3_key, config=business.config)

    return RedirectResponse(presigned_url)
