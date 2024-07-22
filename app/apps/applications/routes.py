from apps.business.routes import AbstractBusinessBaseRouter
from usso.fastapi import jwt_access_security

from .models import Application


class ApplicationRouter(AbstractBusinessBaseRouter[Application]):
    def __init__(self):
        super().__init__(
            model=Application,
            user_dependency=jwt_access_security,
            prefix="/applications",
            tags=["applications"],
        )


router = ApplicationRouter().router
