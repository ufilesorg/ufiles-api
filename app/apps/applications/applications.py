import uuid

from apps.business.models import Business
from apps.files.routes import FilesRouter
from fastapi import Request

from .image import extract_logo_colors


async def color_app(
    request: Request,
    business: Business,
    uid: uuid.UUID,
):
    if isinstance(uid, str):
        uid = uuid.UUID(uid.strip("/"))
    file = await FilesRouter().get_file(request, uid, business)
    return await extract_logo_colors(file)
