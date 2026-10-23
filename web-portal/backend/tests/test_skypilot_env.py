"""export_skypilot_env: ส่งค่า SkyPilot จาก settings ไป os.environ ให้ sky SDK เห็น"""
from app.configs.settings import SKYPILOT_ENV_KEYS, Settings, export_skypilot_env


def _settings(**values) -> Settings:
    # ไม่อ่าน .env จริงของเครื่อง (ค่าบังคับที่ไม่มี default ใส่ค่าเทสให้)
    required = {"SECRET_KEY": "s" * 32, "ADMIN_SESSION_SECRET_KEY": "x" * 32}
    return Settings(_env_file=None, **{**required, **values})


def test_exports_endpoint_and_token(monkeypatch):
    for key in SKYPILOT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    export_skypilot_env(_settings(
        SKYPILOT_API_SERVER_ENDPOINT="https://skypilot.example",
        SKYPILOT_SERVICE_ACCOUNT_TOKEN="sky_test",
    ))

    import os
    assert os.environ["SKYPILOT_API_SERVER_ENDPOINT"] == "https://skypilot.example"
    assert os.environ["SKYPILOT_SERVICE_ACCOUNT_TOKEN"] == "sky_test"


def test_unset_keeps_local_server(monkeypatch):
    for key in SKYPILOT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    export_skypilot_env(_settings())

    import os
    for key in SKYPILOT_ENV_KEYS:
        assert key not in os.environ


def test_existing_environ_wins(monkeypatch):
    monkeypatch.setenv("SKYPILOT_API_SERVER_ENDPOINT", "https://from-shell")

    export_skypilot_env(_settings(SKYPILOT_API_SERVER_ENDPOINT="https://from-dotenv"))

    import os
    assert os.environ["SKYPILOT_API_SERVER_ENDPOINT"] == "https://from-shell"
