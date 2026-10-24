import pytest
from fastapi.testclient import TestClient
from upapi.main import create_app
from upapi.settings import Environment, Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(env=Environment.TEST, log_json=True)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings), raise_server_exceptions=False)
