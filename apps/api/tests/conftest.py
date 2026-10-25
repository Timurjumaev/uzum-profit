import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from upapi.main import create_app
from upapi.settings import Environment, Settings

sys.path.insert(0, str(Path(__file__).parent))
import dbtools

# Testlarda hamma so'rov bitta "IP"dan (``testclient``) — IP cheklovi (B2.10) faqat o'z testida tekshiriladi.
os.environ.setdefault("UP_OTP_PER_IP_HOUR", "100000")


@pytest.fixture
def settings() -> Settings:
    return Settings(env=Environment.TEST, log_json=True)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings), raise_server_exceptions=False)


@pytest.fixture(scope="session")
def db() -> Iterator[dict[str, str]]:
    """Vaqtinchalik baza: up_owner egasi sifatida migratsiya qiladi, ilova up_app bilan ulanadi."""
    with dbtools.migrated_database() as urls:
        yield urls


@pytest.fixture(scope="session")
def seed(db: dict[str, str]) -> dbtools.Seed:
    return dbtools.seed_two_orgs(db["admin"])
