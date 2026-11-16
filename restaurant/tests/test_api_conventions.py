import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from restaurant.app.api import API_PREFIX
from restaurant.app.api.errors import AppError, AppValidationError, ConflictError, NotFoundError
from restaurant.app.api.formatting import utc_iso
from restaurant.app.api.pagination import Pagination, make_page
from restaurant.app.main import create_app
from restaurant.app.settings import Settings

SECRET_SQL = "SELECT * FROM secret_table"


class Item(BaseModel):
    name: str = Field(min_length=1)
    price_cents: int


def build_client(env: str = "test") -> TestClient:
    app = create_app(Settings(env=env))
    r = APIRouter(prefix=API_PREFIX)
    data = list(range(45))

    @r.get("/t/missing")
    def missing():
        raise NotFoundError("Dish 1 not found.")

    @r.get("/t/conflict")
    def conflict():
        raise ConflictError("Already exists.")

    @r.get("/t/invalid")
    def invalid():
        raise AppValidationError("Bad", [{"field": "x", "message": "bad"}])

    @r.get("/t/app")
    def generic_app():
        raise AppError("Nope")

    @r.get("/t/boom")
    def boom():
        raise RuntimeError(f"db exploded: {SECRET_SQL}")

    @r.post("/t/items")
    def create(item: Item):
        return item

    @r.get("/t/list")
    def listing(p: Pagination):
        return make_page(data[p.offset : p.offset + p.limit], len(data), p)

    app.include_router(r)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client():
    return build_client()


def assert_error_shape(r, status, code):
    assert r.status_code == status
    err = r.json()["error"]
    assert err["code"] == code
    assert isinstance(err["message"], str)
    assert err["request_id"] == r.headers["X-Request-ID"]
    assert set(err) <= {"code", "message", "details", "request_id"}
    return err


def test_status_422_validation_has_per_field_details(client):
    r = client.post("/api/v1/t/items", json={"name": "", "price_cents": "abc"})
    err = assert_error_shape(r, 422, "validation_error")
    fields = {d["field"] for d in err["details"]}
    assert fields == {"name", "price_cents"}
    assert "abc" not in r.text  # input is not echoed back


def test_status_422_app_validation_error(client):
    err = assert_error_shape(client.get("/api/v1/t/invalid"), 422, "validation_error")
    assert err["details"] == [{"field": "x", "message": "bad"}]


def test_status_404_not_found(client):
    assert_error_shape(client.get("/api/v1/t/missing"), 404, "not_found")


def test_status_404_unknown_route_same_shape(client):
    assert_error_shape(client.get("/api/v1/nope"), 404, "not_found")


def test_status_405_method_not_allowed_same_shape(client):
    assert_error_shape(client.delete("/api/v1/t/missing"), 405, "method_not_allowed")


def test_status_409_conflict(client):
    assert_error_shape(client.get("/api/v1/t/conflict"), 409, "conflict")


def test_status_400_generic_app_error(client):
    assert_error_shape(client.get("/api/v1/t/app"), 400, "bad_request")


def test_status_500_generic_message_no_leak(client, caplog):
    with caplog.at_level(logging.CRITICAL):
        r = client.get("/api/v1/t/boom")
    err = assert_error_shape(r, 500, "internal_error")
    assert err["message"] == "An unexpected error occurred."
    for leaked in ("db exploded", SECRET_SQL, "Traceback", "RuntimeError", ".py"):
        assert leaked not in r.text


# ---- pagination
def test_pagination_defaults_and_total(client):
    b = client.get("/api/v1/t/list").json()
    assert (b["limit"], b["offset"], b["total"]) == (20, 0, 45)
    assert b["items"] == list(range(20))


def test_pagination_offset_last_page_and_beyond(client):
    assert client.get("/api/v1/t/list?limit=20&offset=40").json()["items"] == [40, 41, 42, 43, 44]
    b = client.get("/api/v1/t/list?offset=100").json()
    assert b["items"] == [] and b["total"] == 45


def test_pagination_max_limit_100_accepted(client):
    b = client.get("/api/v1/t/list?limit=100").json()
    assert b["limit"] == 100 and len(b["items"]) == 45


@pytest.mark.parametrize(
    "q", ["limit=1000", "limit=101", "limit=0", "limit=-1", "offset=-1", "limit=x"]
)
def test_pagination_limit_1000_rejected_with_422(client, q):
    err = assert_error_shape(client.get(f"/api/v1/t/list?{q}"), 422, "validation_error")
    assert err["details"][0]["field"] in ("limit", "offset")


# ---- request id
def test_request_id_valid_incoming_is_echoed_in_header_and_error(client):
    r = client.get("/api/v1/t/missing", headers={"X-Request-ID": "abc-12345_XYZ"})
    assert r.headers["X-Request-ID"] == "abc-12345_XYZ"
    assert r.json()["error"]["request_id"] == "abc-12345_XYZ"


def test_request_id_echoed_on_success(client):
    r = client.get("/healthz", headers={"X-Request-ID": "good-id-0001"})
    assert r.headers["X-Request-ID"] == "good-id-0001"


def test_request_id_generated_when_absent_and_unique(client):
    a = client.get("/healthz").headers["X-Request-ID"]
    b = client.get("/healthz").headers["X-Request-ID"]
    assert a and b and a != b


@pytest.mark.parametrize("bad", ["short", "has space in it", "x" * 65, "bad-id-with-$"])
def test_request_id_invalid_incoming_is_replaced(client, bad):
    r = client.get("/api/v1/t/missing", headers={"X-Request-ID": bad})
    assert r.headers["X-Request-ID"] != bad
    assert r.json()["error"]["request_id"] == r.headers["X-Request-ID"]


def test_request_id_propagates_to_500(client, caplog):
    with caplog.at_level(logging.CRITICAL):
        r = client.get("/api/v1/t/boom", headers={"X-Request-ID": "trace-me-0001"})
    assert r.headers["X-Request-ID"] == "trace-me-0001"
    assert r.json()["error"]["request_id"] == "trace-me-0001"


# ---- docs, CORS, formats
def test_docs_reachable_in_development():
    c = build_client("development")
    assert c.get("/api/docs").status_code == 200
    assert c.get("/api/openapi.json").status_code == 200


def test_docs_not_reachable_in_production():
    c = TestClient(create_app(Settings(env="production", secret_key="a-real-secret")))
    assert c.get("/api/docs").status_code == 404
    assert c.get("/api/openapi.json").status_code == 404


def test_cors_is_off_by_default(client):
    r = client.get("/healthz", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_timestamps_are_iso_8601_utc():
    assert utc_iso(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02T03:04:05Z"
    local = datetime(2026, 1, 2, 5, 4, 5, tzinfo=timezone(timedelta(hours=2)))
    assert utc_iso(local) == "2026-01-02T03:04:05Z"
