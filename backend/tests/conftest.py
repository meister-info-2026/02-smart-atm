"""테스트 공통 설정.

DB는 임시 SQLite 파일을 쓴다 (MySQL이 없어도 전체 흐름을 검증할 수 있게).
환경변수는 backend 모듈을 import 하기 전에 먼저 설정해야 한다.
"""
import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

_TEST_DB = Path(tempfile.gettempdir()) / "smart_atm_test.db"
if _TEST_DB.exists():
    _TEST_DB.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["JWT_SECRET"] = "test-jwt-secret-at-least-32-bytes-long"
os.environ["DEVICE_API_KEY"] = "test-device-key"
os.environ["DEVICE_MODE"] = "mock"
os.environ["SEED_DEFAULT_PASSWORD"] = "test1234"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from db.database import init_db  # noqa: E402
from db.seed import seed  # noqa: E402
from main import app  # noqa: E402

DEVICE_HEADERS = {"X-Device-Api-Key": "test-device-key"}


@pytest.fixture(scope="session")
def device_headers() -> dict[str, str]:
    """라즈베리파이 ATM의 디바이스 인증 헤더."""
    return dict(DEVICE_HEADERS)


@pytest.fixture(scope="session", autouse=True)
def _prepare_db() -> None:
    init_db()
    seed()


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _login(client: TestClient, username: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": "test1234"}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


@pytest.fixture(scope="session")
def user_headers(client: TestClient) -> dict[str, str]:
    """노약자 사용자(김순자)의 인증 헤더."""
    return {"Authorization": f"Bearer {_login(client, 'halmeoni')}"}


@pytest.fixture(scope="session")
def callcenter_headers(client: TestClient) -> dict[str, str]:
    """콜센터 상담원의 인증 헤더."""
    return {"Authorization": f"Bearer {_login(client, 'callcenter')}"}
