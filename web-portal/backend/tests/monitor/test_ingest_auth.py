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
