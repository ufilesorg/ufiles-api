import aiohttp
from apps.business.middlewares import get_business
from apps.business.models import Business
from apps.business.routes import AbstractBusinessBaseRouter
from core import exceptions
from fastapi import Request, Response
from usso.fastapi import jwt_access_security

from .applications import color_app
from .models import Application


class ApplicationRouter(AbstractBusinessBaseRouter[Application, Application]):
    def __init__(self):
        super().__init__(
            model=Application,
            schema=Application,
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

    # url = f"{app.domain}/{path}"
    url = f"{app.domain}/v1/apps/{app.name}/{path}"
    # logging.info(f"Proxying request to {url}")
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
