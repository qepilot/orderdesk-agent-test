import pytest
from fastapi.testclient import TestClient

from restaurant.app.main import create_app
from restaurant.app.settings import Settings, SettingsError


def test_healthz_returns_200_ok():
    client = TestClient(create_app(Settings(env="test")))
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_startup_stops_with_message_naming_variable(monkeypatch):
    monkeypatch.setenv("RESTAURANT_TAX_PERCENT", "oops")
    with pytest.raises(SettingsError, match="RESTAURANT_TAX_PERCENT"):
        create_app()


def test_importing_app_with_bad_settings_exits_with_clear_message(monkeypatch):
    import importlib

    import restaurant.app.main as main

    monkeypatch.setenv("RESTAURANT_ENV", "production")
    monkeypatch.delenv("RESTAURANT_SECRET_KEY", raising=False)
    with pytest.raises(SystemExit, match="RESTAURANT_SECRET_KEY"):
        importlib.reload(main)
    monkeypatch.undo()
    importlib.reload(main)
