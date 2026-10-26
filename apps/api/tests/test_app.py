import json

import pytest
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient
from upapi import __version__
from upapi.errors import PROBLEM_JSON, AppError
from upapi.logs import REDACTED, configure_logging, get_logger
from upapi.main import create_app
from upapi.settings import Environment, Settings


def test_health_both_paths(client: TestClient) -> None:
    for path in ("/health", "/api/v1/health"):
        r = client.get(path)
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "version": __version__, "env": "test"}


def test_request_id_generated_and_propagated(client: TestClient) -> None:
    r = client.get("/health")
    assert len(r.headers["X-Request-ID"]) == 32
    r = client.get("/health", headers={"X-Request-ID": "abc-123-XYZ"})
    assert r.headers["X-Request-ID"] == "abc-123-XYZ"
    bad = client.get(
        "/health", headers={"X-Request-ID": "x\ny"}
    )  # logga xavfli qiymat qabul qilinmaydi
    assert bad.headers["X-Request-ID"] != "x\ny" and len(bad.headers["X-Request-ID"]) == 32


def test_openapi_under_api_prefix(client: TestClient) -> None:
    spec = client.get("/api/v1/openapi.json").json()
    assert spec["info"]["title"] == "SellerMax API"
    assert "/api/v1/health" in spec["paths"]
    assert client.get("/openapi.json").status_code == 404


def _app_with_routes(settings: Settings) -> FastAPI:
    app = create_app(settings)

    @app.get("/api/v1/boom")
    def boom() -> None:
        raise RuntimeError("kutilmagan")

    @app.get("/api/v1/shop")
    def shop() -> None:
        raise AppError("shop_not_found", 404, "Do'kon topilmadi", "id=7")

    @app.get("/api/v1/items")
    def items(limit: int = Query(ge=1, le=100)) -> dict[str, int]:
        return {"limit": limit}

    return app


@pytest.mark.parametrize(
    ("method", "path", "status", "code"),
    [("get", "/api/v1/yoq", 404, "not_found"), ("post", "/health", 405, "method_not_allowed")],
)
def test_http_errors_are_problem_json(
    client: TestClient, method: str, path: str, status: int, code: str
) -> None:
    r = getattr(client, method)(path)
    assert r.status_code == status and r.headers["content-type"] == PROBLEM_JSON
    body = r.json()
    assert body["code"] == code and body["status"] == status
    assert body["type"].endswith("/" + code) and body["instance"] == path
    assert body["request_id"] == r.headers["X-Request-ID"]
    if status == 405:
        assert r.headers["allow"] == "GET"


def test_app_error(settings: Settings) -> None:
    c = TestClient(_app_with_routes(settings))
    body = c.get("/api/v1/shop").json()
    assert body == {
        "type": "https://uzum-profit.uz/problems/shop_not_found",
        "title": "Do'kon topilmadi",
        "status": 404,
        "code": "shop_not_found",
        "detail": "id=7",
        "instance": "/api/v1/shop",
        "request_id": body["request_id"],
    }
    assert AppError("x").title == "Bad Request"


def test_validation_error(settings: Settings) -> None:
    c = TestClient(_app_with_routes(settings))
    r = c.get("/api/v1/items?limit=0")
    assert r.status_code == 422 and r.headers["content-type"] == PROBLEM_JSON
    body = r.json()
    assert body["code"] == "validation_error"
    assert body["errors"][0]["loc"] == ["query", "limit"]
    assert c.get("/api/v1/items?limit=5").json() == {"limit": 5}


@pytest.mark.parametrize(("env", "shows"), [(Environment.TEST, True), (Environment.PROD, False)])
def test_unhandled_error_hides_details_in_prod(
    env: Environment, shows: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    c = TestClient(
        _app_with_routes(Settings(env=env, log_json=True)), raise_server_exceptions=False
    )
    r = c.get("/api/v1/boom", headers={"X-Request-ID": "req-500-test"})
    assert r.status_code == 500 and r.headers["content-type"] == PROBLEM_JSON
    body = r.json()
    assert body["code"] == "internal" and body["request_id"] == "req-500-test"
    assert r.headers["X-Request-ID"] == "req-500-test"
    assert ("detail" in body) is shows
    logged = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    err = next(x for x in logged if x["event"] == "unhandled_error")
    assert err["request_id"] == "req-500-test" and "RuntimeError" in err["exception"]


def test_access_log_json(client: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    client.get("/health", headers={"X-Request-ID": "req-access-1"})
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["event"] == "request" and line["status_code"] == 200
    assert line["request_id"] == "req-access-1" and line["path"] == "/health"
    assert line["level"] == "info" and line["timestamp"].endswith("Z")


def test_secrets_are_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json=True)
    get_logger().info(
        "otp_sent",
        phone="+998901234567",
        code="482915",
        uzum_token="abc",
        headers={"Authorization": "Bearer secret.value", "accept": "json"},
        nested=[{"api_key": "k"}, "Bearer zzz"],
        error_code="validation_error",
        status_code=200,
    )
    line = json.loads(capsys.readouterr().out.strip())
    assert line["code"] == REDACTED and line["uzum_token"] == REDACTED
    assert line["headers"] == {"Authorization": REDACTED, "accept": "json"}
    assert line["nested"] == [{"api_key": REDACTED}, f"Bearer {REDACTED}"]
    assert line["error_code"] == "validation_error" and line["status_code"] == 200
    assert "482915" not in json.dumps(line) and "secret.value" not in json.dumps(line)


def test_console_logs_in_dev(capsys: pytest.CaptureFixture[str]) -> None:
    c = TestClient(create_app(Settings(env=Environment.DEV)))
    c.get("/health")
    out = capsys.readouterr().out
    assert "request" in out and not out.strip().startswith("{")


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UP_ENV", "staging")
    monkeypatch.setenv("UP_LOG_LEVEL", "warning")
    s = Settings()
    assert s.env is Environment.STAGING and s.json_logs and not s.show_error_details
    assert Settings(env=Environment.DEV).json_logs is False
    assert Settings(env=Environment.DEV, log_json=True).json_logs is True
