import uuid

import aiohttp
from apps.business.middlewares import get_business
from apps.business.models import Business
from apps.business.routes import AbstractBusinessBaseRouter
from apps.files.routes import FilesRouter
from core import exceptions
from fastapi import Request, Response
from usso.fastapi import jwt_access_security

from .image import extract_logo_colors
from .models import Application


class ApplicationRouter(AbstractBusinessBaseRouter[Application]):
    def __init__(self):
        super().__init__(
            model=Application,
            user_dependency=jwt_access_security,
            prefix="/apps",
            tags=["applications"],
        )

    async def get_user(self, request: Request, *args, **kwargs):
        user = await super().get_user(request, *args, **kwargs)
        business: Business = await get_business(request)
        if request.method != "GET" and user.uid != business.user_id:
            raise exceptions.BaseHTTPException(
                status_code=403,
                error="Forbidden",
                message="You are not allowed to access this resource",
            )
        return user

    def config_routes(self, **kwargs):
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


router = ApplicationRouter().router


async def proxy_request(
    request: Request,
    app_name: str,
    path: str,
    method: str,
):
    business: Business = await get_business(request)

    app = await Application.find_one(
        Application.name == app_name, Application.business_name == business.name
    )
    if not app:
        raise exceptions.BaseHTTPException(
            status_code=404,
            error="Not Found",
            message=f"Application {app_name} not found",
        )

    url = f"{app.domain}/{path}"
    async with aiohttp.ClientSession() as session:
        async with session.request(
            method=method,
            url=url,
            headers=request.headers,
            params=request.query_params,
            data=await request.body() if method in ["POST", "PUT", "PATCH"] else None,
        ) as response:
            content = await response.read()
            return Response(
                status_code=response.status,
                content=content,
                headers=dict(response.headers),
            )


@router.get("/colors/{uid}")
async def color_app(
    request: Request,
    uid: uuid.UUID,
):
    business: Business = await get_business(request)
    if isinstance(uid, str):
        uid = uuid.UUID(uid.strip("/"))
    file = await FilesRouter().get_file(request, uid, business)
    return await extract_logo_colors(file)


@router.get("/{app_name}/{path:path}")
async def get_app(request: Request, app_name: str, path: str):
    if app_name == "colors":
        return await color_app(request, path)
    return await proxy_request(request, app_name, path, "GET")


@router.post("/{app_name}/{path:path}")
async def post_app(request: Request, app_name: str, path: str):
    return await proxy_request(request, app_name, path, "POST")


@router.put("/{app_name}/{path:path}")
async def put_app(request: Request, app_name: str, path: str):
    return await proxy_request(request, app_name, path, "PUT")


@router.delete("/{app_name}/{path:path}")
async def delete_app(request: Request, app_name: str, path: str):
    return await proxy_request(request, app_name, path, "DELETE")


@router.patch("/{app_name}/{path:path}")
async def patch_app(request: Request, app_name: str, path: str):
    return await proxy_request(request, app_name, path, "PATCH")
