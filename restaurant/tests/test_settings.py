import pytest

from restaurant.app.settings import SettingsError, load_settings


def test_defaults_when_nothing_set():
    s = load_settings({})
    assert s.env == "development"
    assert s.tax_percent == 8
    assert s.delivery_fee_cents == 300
    assert s.db_path.endswith("restaurant.db")


def test_values_read_from_environment():
    s = load_settings(
        {
            "RESTAURANT_ENV": "test",
            "RESTAURANT_DB_PATH": "x.db",
            "RESTAURANT_SECRET_KEY": "abc",
            "RESTAURANT_TAX_PERCENT": "10",
            "RESTAURANT_DELIVERY_FEE_CENTS": "250",
        }
    )
    assert (s.env, s.db_path, s.secret_key, s.tax_percent, s.delivery_fee_cents) == (
        "test", "x.db", "abc", 10, 250,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("RESTAURANT_ENV", "staging"),
        ("RESTAURANT_TAX_PERCENT", "abc"),
        ("RESTAURANT_TAX_PERCENT", "101"),
        ("RESTAURANT_TAX_PERCENT", "-1"),
        ("RESTAURANT_DELIVERY_FEE_CENTS", "-5"),
        ("RESTAURANT_DELIVERY_FEE_CENTS", "1.5"),
        ("RESTAURANT_DB_PATH", "  "),
    ],
)
def test_invalid_setting_error_names_variable(name, value):
    with pytest.raises(SettingsError, match=name):
        load_settings({name: value})


@pytest.mark.parametrize("key", [None, "", "   ", "change-me"])
def test_production_refuses_default_or_empty_secret(key):
    environ = {"RESTAURANT_ENV": "production"}
    if key is not None:
        environ["RESTAURANT_SECRET_KEY"] = key
    with pytest.raises(SettingsError, match="RESTAURANT_SECRET_KEY"):
        load_settings(environ)


def test_production_accepts_real_secret():
    s = load_settings({"RESTAURANT_ENV": "production", "RESTAURANT_SECRET_KEY": "fake-long-secret"})
    assert s.env == "production"


def test_default_secret_allowed_outside_production():
    assert load_settings({"RESTAURANT_ENV": "development"}).secret_key == "change-me"


def test_reads_os_environ_by_default(monkeypatch):
    monkeypatch.setenv("RESTAURANT_TAX_PERCENT", "5")
    assert load_settings().tax_percent == 5
