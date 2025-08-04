import logging
import os
from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from beanie import init_beanie

from server.config import Settings
from server.server import app as fastapi_app


@pytest.fixture(scope="session", autouse=True)
def setup_debugpy() -> None:
    if os.getenv("DEBUGPY", "False").lower() in ("true", "1", "yes"):
        import debugpy  # noqa: T100

        debugpy.listen(("127.0.0.1", 3020))  # noqa: T100
        logging.info("Waiting for debugpy client")
        debugpy.wait_for_client()  # noqa: T100


@pytest.fixture(scope="session")
def mongo_client():  # noqa: ANN201
    from mongomock_motor import AsyncMongoMockClient

    mongo_client = AsyncMongoMockClient()
    yield mongo_client


async def init_db(mongo_client: object) -> None:
    from fastapi_mongo_base.models import BaseEntity
    from fastapi_mongo_base.utils import basic

    database = mongo_client.get_database("test_db")
    await init_beanie(
        database=database,
        document_models=basic.get_all_subclasses(BaseEntity),
    )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def db(mongo_client: object) -> AsyncGenerator[None]:
    Settings.config_logger()
    logging.info("Initializing database")
    await init_db(mongo_client)
    logging.info("Database initialized")
    yield
    logging.info("Cleaning up database")


@pytest_asyncio.fixture(scope="session")
async def client() -> AsyncGenerator[httpx.AsyncClient]:
    """Fixture to provide an AsyncClient for FastAPI app."""

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fastapi_app),
        base_url="https://test.uln.me/api/exchange/v1/",
    ) as ac:
        yield ac


@pytest_asyncio.fixture(scope="session")
async def authenticated_client(
    client: httpx.AsyncClient,
) -> AsyncGenerator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fastapi_app),
        base_url=client.base_url,
        headers={"x-api-key": os.getenv("API_KEY")},  # type: ignore
    ) as ac:
        yield ac
