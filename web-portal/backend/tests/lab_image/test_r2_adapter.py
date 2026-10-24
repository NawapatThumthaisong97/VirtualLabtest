"""
R2Adapter — boto3 config ของ Cloudflare R2 (เซ็น URL ในเครื่อง ไม่ยิง network)
"""
from urllib.parse import parse_qs, urlparse

import pytest

from app.adapters.r2_adapter import R2Adapter, R2NotConfiguredError
from app.configs.settings import settings


@pytest.fixture
def r2_credentials(monkeypatch):
    monkeypatch.setattr(settings, "R2_ACCOUNT_ID", "acct123")
    monkeypatch.setattr(settings, "R2_ENDPOINT_URL", None)
    monkeypatch.setattr(settings, "R2_ACCESS_KEY_ID", "fake-key-id")
    monkeypatch.setattr(settings, "R2_SECRET_ACCESS_KEY", "fake-secret")
    monkeypatch.setattr(settings, "R2_BUCKET_NAME", "my-bucket")


class TestPresignedPutUrl:
    """R2 presigned PUT URL"""

    def test_url_shape(self, r2_credentials):
        """URL targets the account endpoint (path-style) and is SigV4 signed with expiry"""
        url = R2Adapter().generate_presigned_put_url("lab-images/c/i/image.tar", "application/x-tar", 900)
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        assert parsed.scheme == "https"
        assert parsed.netloc == "acct123.r2.cloudflarestorage.com"
        assert parsed.path == "/my-bucket/lab-images/c/i/image.tar"
        assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
        assert query["X-Amz-Expires"] == ["900"]
        assert "auto/s3/aws4_request" in query["X-Amz-Credential"][0]
        assert query["X-Amz-Signature"][0]

    def test_content_type_is_signed(self, r2_credentials):
        """Content-Type is part of the signature, so a client sending another type gets 403 from R2"""
        url = R2Adapter().generate_presigned_put_url("k.tar", "application/x-tar", 900)
        signed = parse_qs(urlparse(url).query)["X-Amz-SignedHeaders"][0].split(";")
        assert "content-type" in signed

    def test_if_none_match_is_signed(self, r2_credentials):
        """If-None-Match is part of the signature, so R2 only accepts the first PUT for a key (later ones get 412)"""
        url = R2Adapter().generate_presigned_put_url("k.tar", "application/x-tar", 900)
        signed = parse_qs(urlparse(url).query)["X-Amz-SignedHeaders"][0].split(";")
        assert "if-none-match" in signed

    def test_default_expiry_comes_from_settings(self, r2_credentials, monkeypatch):
        """Without an explicit expiry the R2_PRESIGN_EXPIRES_SECONDS setting is used"""
        monkeypatch.setattr(settings, "R2_PRESIGN_EXPIRES_SECONDS", 1200)
        url = R2Adapter().generate_presigned_put_url("k.tar", "application/x-tar")
        assert parse_qs(urlparse(url).query)["X-Amz-Expires"] == ["1200"]

    def test_explicit_endpoint_url_wins(self, r2_credentials, monkeypatch):
        """R2_ENDPOINT_URL overrides the endpoint derived from the account id"""
        monkeypatch.setattr(settings, "R2_ENDPOINT_URL", "https://custom.example.com")
        url = R2Adapter().generate_presigned_put_url("k.tar", "application/x-tar", 60)
        assert urlparse(url).netloc == "custom.example.com"


class TestNotConfigured:
    """R2 adapter without configuration"""

    @pytest.mark.parametrize(
        "missing", ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"]
    )
    def test_missing_setting_raises(self, r2_credentials, monkeypatch, missing):
        """Any missing R2 setting raises R2NotConfiguredError instead of using AWS default credentials"""
        monkeypatch.setattr(settings, missing, None)
        with pytest.raises(R2NotConfiguredError):
            R2Adapter().generate_presigned_put_url("k.tar", "application/x-tar", 60)

    def test_import_does_not_require_config(self):
        """Creating the adapter object never touches settings, only first use does"""
        R2Adapter()
