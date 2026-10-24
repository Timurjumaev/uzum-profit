import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from upapi.main import create_app
from upapi.settings import Environment, Settings

sys.path.insert(0, str(Path(__file__).parent))
import dbtools


@pytest.fixture
def settings() -> Settings:
    return Settings(env=Environment.TEST, log_json=True)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings), raise_server_exceptions=False)


@pytest.fixture(scope="session")
def db() -> Iterator[dict[str, str]]:
    """Vaqtinchalik baza: up_owner egasi sifatida migratsiya qiladi, ilova up_app bilan ulanadi."""
    dbtools.require_admin()
    name = f"up_test_{uuid.uuid4().hex[:10]}"
    urls = dbtools.create_database(name)
    try:
        dbtools.alembic(urls["owner"], "upgrade", "head")
        yield urls
    finally:
        dbtools.drop_database(name)


@pytest.fixture(scope="session")
def seed(db: dict[str, str]) -> dbtools.Seed:
    return dbtools.seed_two_orgs(db["admin"])
