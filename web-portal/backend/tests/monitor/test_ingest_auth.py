"""
regression: POST /api/v1/logs ต้องใช้ token ของ admin เท่านั้น
เดิมยอมรับ SECRET_KEY ตรง ๆ เป็น token และยอมให้ localhost ส่งโดยไม่มี token (ปิด 2026-10-24)
"""
from types import SimpleNamespace as _ns

import pytest

from app.configs.settings import settings
from app.exceptions.domain import DomainError, InvalidTokenError
from app.routes.monitor_route import verify_log_ingest_permission


def request(host):
    return _ns(client=_ns(host=host), cookies={})


class TestIngestAuth:
    """Log ingest: no shortcuts around a real admin token"""

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
    def test_localhost_without_token_rejected(self, db, host):
        """regression: request from localhost with no token -> 401 (used to pass)"""
        with pytest.raises(InvalidTokenError):
            verify_log_ingest_permission(request(host), credentials=None, x_collector_token=None, db=db)

    def test_secret_key_as_token_rejected(self, db):
        """regression: SECRET_KEY itself as bearer token -> rejected (used to pass)"""
        creds = _ns(credentials=settings.SECRET_KEY)
        with pytest.raises(DomainError):
            verify_log_ingest_permission(request("100.64.0.5"), credentials=creds, x_collector_token=None, db=db)

    def test_secret_key_as_collector_header_rejected(self, db):
        """regression: SECRET_KEY in X-Collector-Token -> rejected"""
        with pytest.raises(DomainError):
            verify_log_ingest_permission(request("127.0.0.1"), credentials=None,
                                         x_collector_token=settings.SECRET_KEY, db=db)


COLLECTOR = "c" * 40


class TestCollectorToken:
    """SIEM_COLLECTOR_TOKEN: Vector / Falco / Sigma send logs without an admin JWT"""

    def test_collector_token_accepted(self, db, monkeypatch):
        """X-Collector-Token equal to SIEM_COLLECTOR_TOKEN -> allowed"""
        monkeypatch.setattr(settings, "SIEM_COLLECTOR_TOKEN", COLLECTOR)
        assert verify_log_ingest_permission(request("100.83.96.97"), credentials=None,
                                            x_collector_token=COLLECTOR, db=db) is True

    def test_collector_token_as_bearer_accepted(self, db, monkeypatch):
        """Same token as Authorization: Bearer -> allowed"""
        monkeypatch.setattr(settings, "SIEM_COLLECTOR_TOKEN", COLLECTOR)
        assert verify_log_ingest_permission(request("100.83.96.97"), credentials=_ns(credentials=COLLECTOR),
                                            x_collector_token=None, db=db) is True

    def test_wrong_collector_token_rejected(self, db, monkeypatch):
        """Different token -> rejected"""
        monkeypatch.setattr(settings, "SIEM_COLLECTOR_TOKEN", COLLECTOR)
        with pytest.raises(DomainError):
            verify_log_ingest_permission(request("100.83.96.97"), credentials=None,
                                         x_collector_token="x" * 40, db=db)

    def test_not_set_rejects_everything_but_admin(self, db, monkeypatch):
        """Not set -> any collector token rejected"""
        monkeypatch.setattr(settings, "SIEM_COLLECTOR_TOKEN", None)
        with pytest.raises(DomainError):
            verify_log_ingest_permission(request("100.83.96.97"), credentials=None,
                                         x_collector_token=COLLECTOR, db=db)

    @pytest.mark.parametrize("bad", ["short", None])
    def test_short_or_secret_key_collector_token_ignored(self, db, monkeypatch, bad):
        """Short token, or token equal to SECRET_KEY -> not accepted as collector token"""
        value = bad or settings.SECRET_KEY
        monkeypatch.setattr(settings, "SIEM_COLLECTOR_TOKEN", value)
        with pytest.raises(DomainError):
            verify_log_ingest_permission(request("100.83.96.97"), credentials=None,
                                         x_collector_token=value, db=db)
