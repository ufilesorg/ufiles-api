import httpx
from apps.business.middlewares import get_business
from apps.business.models import Business
from fastapi import Depends, Query, Request, Response
from fastapi_mongo_base.core import exceptions
from fastapi_mongo_base.schemas import PaginatedResponse
from server.config import Settings

# from apps.business.routes import AbstractBusinessBaseRouter
from ufaas_fastapi_business.routes import AbstractBusinessBaseRouter
from usso.fastapi import jwt_access_security

from .applications import color_app
from .models import Application
from .schemas import ApplicationSchema


class ApplicationRouter(AbstractBusinessBaseRouter[Application, ApplicationSchema]):
    def __init__(self):
        super().__init__(
            model=Application,
            schema=ApplicationSchema,
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
        self.router.add_api_route(
            "/search",
            self.search,
            methods=["GET"],
            response_model=self.list_response_schema,
            status_code=200,
        )

    async def list_items(
        self,
        request: Request,
        offset: int = Query(0, ge=0),
        limit: int = Query(10, ge=1, le=Settings.page_max_limit),
        business: Business = Depends(get_business),
    ):
        return await super().list_items(request, offset, limit, business)

    async def search(
        self,
        request: Request,
        q: str = Query(None, description="Search query"),
        offset: int = Query(0, ge=0),
        limit: int = Query(10, ge=1, le=Settings.page_max_limit),
        business: Business = Depends(get_business),
    ):
        apps = await Application.search(business.name, q)
        return PaginatedResponse(
            items=apps[offset : offset + limit],
            total=len(apps),
            offset=offset,
            limit=limit,
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

    url = f"{app.domain}/v1/apps/{app.name}/{path}"
    headers = dict(request.headers)
    headers["x-original-host"] = request.url.hostname
    headers.pop("host", None)
    body = await request.body()

    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=method,
            url=url,
            headers=request.headers,
            params=request.query_params,
            data=body,
            timeout=None,
        )
        return Response(
            status_code=response.status_code,
            content=response.content,
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


@router.patch("/{app_name}/{path:path}")
async def patch_app(request: Request, app_name: str, path: str):
    return await proxy_request(request, app_name, path, "PATCH")


@router.delete("/{app_name}/{path:path}")
async def delete_app(request: Request, app_name: str, path: str):
    return await proxy_request(request, app_name, path, "DELETE")
