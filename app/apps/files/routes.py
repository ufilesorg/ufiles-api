import re
from datetime import datetime
from typing import Never
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Body, File, Request, UploadFile
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from fastapi_mongo_base.core.exceptions import BaseHTTPException
from fastapi_mongo_base.schemas import PaginatedResponse
from fastapi_mongo_base.utils import usso_routes
from usso import UserData
from usso.exceptions import PermissionDenied, USSOException
from usso.integrations.fastapi import USSOAuthentication

from server.config import Settings

from .file_manager import file_manager
from .models import FileMetaData
from .schemas import (
    FileMetaDataSchema,
    FileMetaDataUpdate,
    MultiPartOut,
    PartUploadOut,
    PermissionEnum,
    VolumeOut,
)

usso_auth = USSOAuthentication(raise_exception=False)


class FilesRouter(usso_routes.AbstractTenantUSSORouter):
    model = FileMetaData
    schema = FileMetaDataSchema

    def __init__(self) -> None:
        super().__init__(
            user_dependency=usso_auth,
            prefix="/f",
            tags=["files"],
        )

    def config_schemas(self, schema: type, **kwargs: object) -> None:
        super().config_schemas(
            schema,
            list_item_schema=FileMetaDataSchema,
            retrieve_response_schema=None,
        )

    def config_routes(self) -> None:
        self.router.add_api_route(
            "/",
            self.list_items,
            methods=["GET"],
            response_model=PaginatedResponse[FileMetaDataSchema],
        )
        self.router.add_api_route(
            "/volume",
            self.get_volume,
            methods=["GET"],
            response_model=VolumeOut,
        )
        # self.router.add_api_route(
        #     "/{uid}",
        #     self.retrieve_item,
        #     methods=["GET"],
        #     # response_model=FileMetaDataSignedUrl,
        # )
        # self.router.add_api_route(
        #     "/{uid}/{path:path}",
        #     self.retrieve_item,
        #     methods=["GET"],
        #     # response_model=FileMetaDataSignedUrl,
        # )
        self.router.add_api_route(
            "/{uid}/{path:path}",
            self.head_item,
            methods=["HEAD"],
            # response_model=FileMetaDataSignedUrl,
        )
        self.router.add_api_route(
            "/{uid}",
            self.change_item,
            methods=["PUT"],
            response_model=FileMetaDataSchema,
        )
        self.router.add_api_route(
            "/upload",
            self.upload_file,
            methods=["POST"],
            response_model=FileMetaDataSchema,
        )
        self.router.add_api_route(
            "/upload_base64",
            self.upload_file_base64,
            methods=["POST"],
            response_model=FileMetaDataSchema,
        )
        self.router.add_api_route(
            "/upload_url",
            self.upload_url,
            methods=["POST"],
            response_model=FileMetaDataSchema,
        )
        self.router.add_api_route(
            "/multipart",
            self.start_multipart,
            methods=["POST"],
            response_model=MultiPartOut,
        )
        self.router.add_api_route(
            "/multipart/{upload_id:str}",
            self.upload_part,
            methods=["POST"],
            response_model=PartUploadOut,
        )
        self.router.add_api_route(
            "/multipart/{upload_id:str}/complete",
            self.finish_multipart,
            methods=["POST"],
            response_model=FileMetaDataSchema,
        )

    async def list_items(
        self,
        request: Request,
        *,
        offset: int = 0,
        limit: int = 50,
        parent_id: str | None = None,
        filename: str | None = None,
        filehash: str | None = None,
        is_deleted: bool = False,
        is_directory: bool | None = None,
        user_id: str | None = None,
        content_type: str | None = None,
    ) -> PaginatedResponse[FileMetaDataSchema]:
        user: UserData | None = await self.get_user(request)

        root_permission = False
        if not user:
            user_id = None
        # TODO: check if user is root
        elif self.authorize(action="read", user=user):
            user_id = user.uid
            root_permission = True

        params = dict(request.query_params)
        params.pop("user_id", None)
        params.pop("root_permission", None)
        return await self._list_items(
            request, **params, user_id=user_id, root_permission=root_permission
        )

    async def get_volume(
        self,
        request: Request,
    ) -> VolumeOut:
        user: UserData = await self.get_user(request)
        if not user:
            raise BaseHTTPException(
                status_code=401, error="unauthorized", detail="Unauthorized"
            )

        volume = await FileMetaData.get_volume(user.uid)
        return VolumeOut(volume=volume)

    async def get_file(
        self,
        request: Request,
        uid: str,
        user_id: str | None = None,
    ) -> FileMetaData:
        try:
            user: UserData = await self.get_user(request)
        except USSOException:
            user = None

        root_permission = self.authorize(action="read", user=user)

        if not user:
            user_id = None
        elif self.authorize(action="read", user=user):
            user_id = user.uid
            root_permission = True

        file: FileMetaData = await FileMetaData.get_item(
            user_id=user_id, uid=uid, root_permission=root_permission
        )

        if file is None:
            raise BaseHTTPException(
                status_code=404, error="file_not_found", detail="File not found"
            )

        if not file.user_permission(
            user.uid if user else None
        ).read or not self.authorize(
            action="read", user=user, filter_data=file.model_dump()
        ):
            raise BaseHTTPException(
                status_code=404, error="file_not_found", detail="File not found"
            )

        return file

    async def retrieve_item(  # noqa: ANN201
        self,
        request: Request,
        uid: str,
        signed_url: bool = False,
        details: bool = False,
    ):
        file: FileMetaData = await self.get_file(request, uid)

        if details:
            return FileMetaDataSchema(
                **file.model_dump(), url=file.url, icon=file.icon, preview=file.preview
            )

        if file.is_directory:
            return await self.list_items(
                request=request,
                parent_id=file.uid,
                offset=0,
                limit=Settings.page_max_limit,
            )

        file.access_at = datetime.now()
        await file.save()

        if signed_url:
            presigned_url = await file_manager.generate_presigned_url(file)
            return RedirectResponse(presigned_url)

        range_header = request.headers.get("Range")
        file_size = file.size

        if range_header:
            # Parse the Range header (e.g., "bytes=0-1023")
            range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if not range_match:
                raise BaseHTTPException(
                    status_code=400,
                    error="invalid_range_header",
                    detail="Invalid Range header",
                )

            start = int(range_match.group(1))
            end = int(range_match.group(2)) if range_match.group(2) else file_size - 1

            if start >= file_size or end >= file_size:
                return Response(
                    status_code=416,
                    headers={"Content-Range": f"bytes */{file_size}"},
                )

            chunk_size = end - start + 1
        else:
            start = None
            end = None
            chunk_size = None

        stream = file_manager.stream_file(file, start=start, end=end)

        headers = {
            "Content-Range": (
                f"bytes {start}-{end}/{file_size}" if start else f"bytes */{file_size}"
            ),
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Disposition": (f"inline; filename*=UTF-8''{quote(file.filename)}"),
            "Content-Type": file.content_type,
            # httpchecksum
        }

        return StreamingResponse(
            stream,
            status_code=206 if start else 200,
            headers=headers,
        )

    async def head_item(self, request: Request, uid: str) -> Response:
        file: FileMetaData = await self.get_file(request, uid)
        headers = {
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(file.filename)}",
            "Content-length": str(file.size),
            "Accept-Ranges": "bytes",
        }
        return Response(headers=headers)

    # async def create_item(
    #     self,
    #     request: Request,
    #     data: FileMetaDataCreate,
    # ) -> FileMetaData:
    #     user_id = await self.get_user_id(request)
    #     item = FileMetaData(
    #         user_id=user_id,
    #         access_at=datetime.now(),
    #         **data.model_dump(exclude_none=True, exclude_unset=True),
    #     )
    #     await item.save()
    #     return item

    async def change_item(
        self,
        request: Request,
        uid: str,
        blocking: bool = False,
        file: UploadFile = File(...),  # noqa: B008
        overwrite: bool = False,
    ) -> FileMetaData:
        user: UserData = await self.get_user(request)
        item: FileMetaData = await self.get_file(request, uid)

        if not item.user_permission(user.uid).write or not self.authorize(
            action="update", user=user, filter_data=item.model_dump()
        ):
            raise PermissionDenied(
                detail="You don't have permission to update this file",
            )

        if item.is_deleted:
            raise BaseHTTPException(
                status_code=400,
                error="file_deleted",
                detail="File is deleted",
            )

        meta_data = await file_manager.change_file(
            file=file, file_metadata=item, blocking=blocking, overwrite=overwrite
        )
        return FileMetaDataSchema(**meta_data.model_dump())

    async def update_item(
        self,
        request: Request,
        uid: str,
        update: FileMetaDataUpdate,
    ) -> FileMetaData:
        user: UserData = await self.get_user(request)
        item: FileMetaData = await self.get_file(request, uid)

        if (
            item.user_permission(user.uid).permission
            < (
                PermissionEnum.MANAGE
                if update.need_manage_permissions
                else PermissionEnum.WRITE
            )
        ) or (
            not self.authorize(
                action=("manage" if update.need_manage_permissions else "update"),
                user=user,
                filter_data=item.model_dump(),
            )
        ):
            raise PermissionDenied(
                detail="You don't have permission to update this file",
            )

        if update.is_deleted is not None:
            if item.is_deleted and not update.is_deleted:
                await item.restore(user.uid)
            elif not item.is_deleted and update.is_deleted:
                await item.delete(user.uid)
        if update.filename:
            item.filename = update.filename
        if update.parent_id:
            existing: list[FileMetaData] = await FileMetaData.list_items(
                user_id=user.uid,
                uid=update.parent_id,
            )
            if not existing or not existing[0].is_directory:
                raise BaseHTTPException(
                    status_code=404,
                    error="parent_not_found",
                    detail="Parent directory not found",
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
        uid: str,
    ) -> FileMetaData:
        user: UserData = await self.get_user(request)
        file: FileMetaData = await self.get_file(request, uid)

        if not file.user_permission(user.uid).delete or not self.authorize(
            action="delete", user=user, filter_data=file.model_dump()
        ):
            raise PermissionDenied(
                detail="You don't have permission to delete this file",
            )

        await file.delete(user_id=user.uid)
        return file

    async def upload_file(
        self: Request,
        # user: UserData = Depends(jwt_access_security),
        #
        user_id: str | None = Body(default=None),
        blocking: bool = False,
        file: UploadFile = File(..., description="The file to upload"),  # noqa: B008
        parent_id: str | None = Body(default=None),
        filename: str | None = Body(default=None),
    ) -> FileMetaDataSchema:
        user: UserData = await usso_auth(self)

        if user is None:
            raise USSOException(status_code=401, error="unauthorized")

        form_data = dict(await self.form())
        form_data.pop("user_id", None)
        form_data.pop("parent_id", None)
        form_data.pop("filename", None)
        file = form_data.pop("file", file)

        file_metadata = await file_manager.process_file(
            file=file,
            user_id=user_id,
            blocking=blocking,
            parent_id=parent_id,
            filename=filename,
            **form_data,
        )
        await file_metadata.save()

        return file_metadata

    async def upload_file_base64(
        self,
        request: Request,
        # user: UserData = Depends(jwt_access_security),
        #
        user_id: str | None = Body(default=None),
        blocking: bool = False,
        file: str = Body(default=None),
        parent_id: str | None = Body(default=None),
        filename: str | None = Body(default=None),
        mime_type: str | None = Body(default=None),
    ) -> FileMetaDataSchema:
        import base64
        from io import BytesIO

        if mime_type is None and not file.startswith("data:"):
            raise BaseHTTPException(
                status_code=400,
                error="mime_type_required",
                detail="Mime type is required",
            )
        if mime_type is None:
            mime_type = file.split(";")[0].split(":")[1]
            file = file.split(";")[1]
        file_bytes = BytesIO(base64.b64decode(file))
        uploading_file = UploadFile(file=file_bytes, filename=filename or "file")
        return await self.upload_file(
            request, user_id, blocking, uploading_file, parent_id, filename
        )

    async def upload_url(
        self,
        request: Request,
        url: str = Body(),
        user_id: str | None = Body(default=None),
        blocking: bool = False,
        parent_id: str | None = Body(default=None),
        filename: str | None = Body(default=None),
    ) -> FileMetaDataSchema:
        user: UserData = await usso_auth(request)

        if user is None:
            raise USSOException(status_code=401, error="unauthorized")

        async with httpx.AsyncClient() as client:
            file = await client.get(url, follow_redirects=True)
        uploading_file = UploadFile(file=file, filename=filename or url.split("/")[-1])
        return await self.upload_file(
            request, user_id, blocking, uploading_file, parent_id, filename
        )

    async def start_multipart(
        self,
        request: Request,
        parent_id: str | None = Body(default=None),
        filename: str | None = Body(default=None),
        filehash: str = Body(),
    ) -> Never:
        user: UserData = await usso_auth(request)
        if user is None:
            raise USSOException(status_code=401, error="unauthorized")

        raise NotImplementedError("Multipart upload is not implemented yet")

    async def upload_part(
        self,
        request: Request,
        upload_id: str,
        part: UploadFile = File(..., description="The part to upload"),  # noqa: B008
        part_number: int = Body(),
        blocking: bool = False,
    ) -> Never:
        user: UserData = await usso_auth(request)
        if user is None:
            raise USSOException(status_code=401, error="unauthorized")

        raise NotImplementedError("Multipart upload is not implemented yet")

    async def finish_multipart(
        self,
        request: Request,
        upload_id: str,
    ) -> Never:
        user: UserData = await usso_auth(request)
        if user is None:
            raise USSOException(status_code=401, error="unauthorized")

        raise NotImplementedError("Multipart upload is not implemented yet")


router = FilesRouter().router
download_router = APIRouter(prefix="/d", tags=["files"])


@download_router.get(
    "/{uid:uuid}/{path:path}",
    include_in_schema=False,
    response_class=RedirectResponse | StreamingResponse,
)
@download_router.get(
    "/{uid:uuid}",
    include_in_schema=False,
    response_class=RedirectResponse | StreamingResponse,
)
async def download_file_endpoint(
    request: Request,
    uid: str,
    signed_url: bool = False,
) -> object:  # -> StreamingResponse | RedirectResponse:
    file = await FilesRouter().get_file(request, uid)

    if file.is_directory:
        raise BaseHTTPException(
            status_code=400,
            error="directory_is_not_downloadable",
            detail="Directory is not downloadable",
        )

    file.access_at = datetime.now()
    await file.save()

    if signed_url:
        presigned_url = await file_manager.generate_presigned_url(file)

        return RedirectResponse(presigned_url)

    return StreamingResponse(
        file_manager.stream_file(file),
        media_type=file.content_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{quote(file.filename)}"
            ),
            "Content-length": str(file.size),
        },
    )
