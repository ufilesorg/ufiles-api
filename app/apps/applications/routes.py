from usso.fastapi import jwt_access_security

import aiohttp
from apps.business.routes import AbstractBusinessBaseRouter
from core import exceptions
from fastapi import Response, Request

from .models import Application


class ApplicationRouter(AbstractBusinessBaseRouter[Application]):
    def __init__(self):
        super().__init__(
            model=Application,
            user_dependency=jwt_access_security,
            prefix="/apps",
            tags=["applications"],
        )


router = ApplicationRouter().router


@router.get("/{app_name}/{path:path}")
async def get_app(request: Request, app_name: str, path: str):
    app = await Application.find_one(Application.name == app_name)
    if not app:
        raise exceptions.BaseHTTPException(
            status_code=404,
            error="Not Found",
            message=f"Application {app_name} not found",
        )

    url = f"{app.domain}/{path}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=request.headers, params=request.query_params) as response:
            return Response(
                status_code=response.status,
                content=await response.read(),
                headers=response.headers,
            )
