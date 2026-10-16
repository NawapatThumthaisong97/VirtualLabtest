"""
SSO Integration & JWT Generation tests (Issue #77)
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from jose import jwt

from app.adapters import sso_adapter as sso_adapter_module
from app.adapters.sso_adapter import SSOUserInfo
from app.configs.db import get_db
from app.configs.settings import settings
from app.exceptions.domain import (
    ConflictError,
    DomainError,
    ForbiddenError,
    InternalServerError,
    InvalidEmailDomainError,
    InvalidTokenError,
    NotFoundError,
    SSOAuthenticationError,
    UnauthorizedError,
    ValidationError,
)
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.routes.auth_route import router as auth_router
from app.services.auth_service import AuthService
from app.utils.security import hash_password
from tests.fakes import FakeGoogleSSO

STATUS_MAP = {
    NotFoundError: 404,
    ConflictError: 409,
    ForbiddenError: 403,
    UnauthorizedError: 401,
    ValidationError: 400,
    InternalServerError: 500,
}


@pytest.fixture(autouse=True)
def sso_settings(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_EMAIL_DOMAINS_STR", "dome.tu.ac.th,tu.ac.th")
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-key-for-jwt")
    monkeypatch.setattr(settings, "ALGORITHM", "HS256")
    monkeypatch.setattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 30)


@pytest.fixture
def fake_sso(monkeypatch):
    fake = FakeGoogleSSO()
    monkeypatch.setattr(sso_adapter_module, "sso_adapter", fake)
    return fake


@pytest.fixture
def client(db, fake_sso):
    test_app = FastAPI()

    @test_app.exception_handler(DomainError)
    async def _domain_error_handler(request, exc: DomainError):
        status_code = 500
        for error_type, code in STATUS_MAP.items():
            if isinstance(exc, error_type):
                status_code = code
                break
        return JSONResponse(
            status_code=status_code,
            content={
                "success": False,
                "message": exc.message,
                "data": None,
                "error": {"code": exc.code, "message": exc.message},
            },
        )

    test_app.include_router(auth_router, prefix="/api")
    test_app.dependency_overrides[get_db] = lambda: db
    return TestClient(test_app)


class TestUniversityEmailDomain:
    """Validate university email domain rules"""

    @pytest.mark.parametrize(
        "raw_email,expected",
        [
            ("sophia.dav@dome.tu.ac.th", "sophia.dav@dome.tu.ac.th"),
            ("  SOPHIA.DAV@DOME.TU.AC.TH  ", "sophia.dav@dome.tu.ac.th"),
            ("kittipong@tu.ac.th", "kittipong@tu.ac.th"),
        ],
    )
    def test_valid_university_domains_accepted(self, raw_email, expected):
        """Emails under dome.tu.ac.th or tu.ac.th are normalized and accepted"""
        assert AuthService.validate_university_email(raw_email) == expected

    @pytest.mark.parametrize(
        "external_email",
        [
            "outsider@gmail.com",
            "student@hotmail.com",
            "evil@notdome.tu.ac.th",
            "dome.tu.ac.th@gmail.com",
            "user@dome.tu.ac.th.attacker.com",
        ],
    )
    def test_non_university_domains_rejected(self, external_email):
        """Non-university or spoofed domains raise InvalidEmailDomainError (403)"""
        with pytest.raises(InvalidEmailDomainError):
            AuthService.validate_university_email(external_email)

    @pytest.mark.parametrize(
        "bad_email",
        [
            "",
            "   ",
            "plain-string",
            "@dome.tu.ac.th",
            "user@",
            "user@@dome.tu.ac.th",
            "user name@dome.tu.ac.th",
        ],
    )
    def test_malformed_email_rejected(self, bad_email):
        """Malformed or empty email raises SSOAuthenticationError (401)"""
        with pytest.raises(SSOAuthenticationError):
            AuthService.validate_university_email(bad_email)


class TestJWTPayloadGeneration:
    """Generate and verify JWT access tokens with role and safe user claims"""

    @pytest.mark.parametrize(
        "role,expected_role",
        [
            (UserRole.STUDENT, "student"),
            (UserRole.INSTRUCTOR, "instructor"),
            (UserRole.ADMIN, "admin"),
        ],
    )
    def test_jwt_contains_role_and_user_info(self, role, expected_role):
        """JWT payload includes sub, email, name, student_id, role, iat, and exp"""
        user = User(
            id=uuid.uuid4(),
            email="sophia.dav@dome.tu.ac.th",
            name="Sophia Davis",
            student_id="6709616000",
            password_hash=hash_password("secret-pass"),
            role=role,
        )
        service = AuthService(db=None, user_repo=None)

        token = service.create_access_token(user)
        payload = service.decode_access_token(token)

        assert payload["sub"] == str(user.id)
        assert payload["email"] == "sophia.dav@dome.tu.ac.th"
        assert payload["name"] == "Sophia Davis"
        assert payload["student_id"] == "6709616000"
        assert payload["role"] == expected_role
        assert isinstance(payload["iat"], int)
        assert isinstance(payload["exp"], int)
        assert payload["exp"] > payload["iat"]

    def test_jwt_excludes_sensitive_secrets(self):
        """JWT payload never contains password_hash, password, or secret keys"""
        user = User(
            id=uuid.uuid4(),
            email="admin@dome.tu.ac.th",
            name="Virtual Lab Admin",
            student_id=None,
            password_hash=hash_password("top-secret-password"),
            role=UserRole.ADMIN,
        )
        service = AuthService(db=None, user_repo=None)

        token = service.create_access_token(user)
        payload = jwt.get_unverified_claims(token)

        forbidden_keys = {"password", "password_hash", "secret", "secret_key", "api_key"}
        assert forbidden_keys.isdisjoint(payload.keys())
        assert "top-secret-password" not in str(payload.values())
        assert user.password_hash not in str(payload.values())

    def test_expired_or_tampered_jwt_rejected(self):
        """Expired or tampered JWT raises InvalidTokenError"""
        service = AuthService(db=None, user_repo=None)
        expired_token = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "role": "student",
                "exp": int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp()),
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )

        with pytest.raises(InvalidTokenError):
            service.decode_access_token(expired_token)

        with pytest.raises(InvalidTokenError):
            service.decode_access_token(expired_token + "tampered")


class TestSSOEndpoints:
    """SSO login and callback endpoints with DB user lookup and provisioning"""

    def test_sso_login_existing_instructor_preserves_role(self, db, client, fake_sso):
        """Existing instructor logging in via Google OAuth2 code receives instructor role in JWT"""
        instructor = User(
            id=uuid.uuid4(),
            email="kittipong.som@dome.tu.ac.th",
            name="Dr. Kittipong Somsak",
            role=UserRole.INSTRUCTOR,
        )
        db.add(instructor)
        db.commit()

        fake_sso.codes["valid-google-code"] = SSOUserInfo(
            email="kittipong.som@dome.tu.ac.th",
            name="Dr. Kittipong Somsak",
            email_verified=True,
            hd="dome.tu.ac.th",
        )

        resp = client.post("/api/auth/sso", json={"code": "valid-google-code"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

        token = body["data"]["accessToken"]
        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert claims["sub"] == str(instructor.id)
        assert claims["email"] == "kittipong.som@dome.tu.ac.th"
        assert claims["role"] == "instructor"
        assert "password_hash" not in claims

    def test_sso_login_provisions_first_time_university_student(self, db, client, fake_sso):
        """First-time university user via SSO is auto-created as student and can call /api/me"""
        fake_sso.id_tokens["google-id-token-1"] = SSOUserInfo(
            email="6709616099@dome.tu.ac.th",
            name="New TU Student",
            email_verified=True,
            hd="dome.tu.ac.th",
        )

        resp = client.post("/api/auth/sso/callback", json={"idToken": "google-id-token-1"})
        assert resp.status_code == 200
        token = resp.json()["data"]["accessToken"]

        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert claims["email"] == "6709616099@dome.tu.ac.th"
        assert claims["name"] == "New TU Student"
        assert claims["student_id"] == "6709616099"
        assert claims["role"] == "student"

        me_resp = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.status_code == 200
        me_data = me_resp.json()["data"]
        assert me_data["email"] == "6709616099@dome.tu.ac.th"
        assert me_data["studentId"] == "6709616099"
        assert me_data["role"] == "student"

    def test_sso_login_rejects_non_university_email(self, db, client, fake_sso):
        """Google login with non-university email (@gmail.com) is rejected with 403"""
        fake_sso.codes["gmail-code"] = SSOUserInfo(
            email="intruder@gmail.com",
            name="External User",
            email_verified=True,
        )

        resp = client.post("/api/auth/sso", json={"code": "gmail-code"})
        assert resp.status_code == 403
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "invalid_email_domain"
        assert UserRepository(db).find_by_email("intruder@gmail.com") is None

    def test_sso_login_rejects_unverified_email_or_bad_code(self, db, client, fake_sso):
        """Unverified SSO email or invalid OAuth code returns 401"""
        resp_bad = client.post("/api/auth/sso", json={"code": "expired-code"})
        assert resp_bad.status_code == 401
        assert resp_bad.json()["error"]["code"] == "sso_authentication_failed"

        resp_unverified = client.post(
            "/api/auth/sso",
            json={
                "email": "sophia.dav@dome.tu.ac.th",
                "name": "Sophia Davis",
                "emailVerified": False,
            },
        )
        assert resp_unverified.status_code == 401
        assert resp_unverified.json()["error"]["code"] == "sso_authentication_failed"

    def test_sso_callback_get_and_forwarded_header(self, db, client, fake_sso):
        """GET /api/auth/sso/callback supports both query code and X-Forwarded-Email header"""
        admin = User(
            id=uuid.uuid4(),
            email="admin@dome.tu.ac.th",
            name="Virtual Lab Admin",
            role=UserRole.ADMIN,
        )
        db.add(admin)
        db.commit()

        resp = client.get(
            "/api/auth/sso/callback",
            headers={"X-Forwarded-Email": "admin@dome.tu.ac.th"},
        )
        assert resp.status_code == 200
        token = resp.json()["data"]["accessToken"]
        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert claims["role"] == "admin"
        assert claims["email"] == "admin@dome.tu.ac.th"

    def test_sso_authorize_url_endpoint(self, client):
        """GET /api/auth/sso/login returns Google OAuth2 authorization URL with university hd"""
        resp = client.get("/api/auth/sso/login?state=xyz123")
        assert resp.status_code == 200
        url = resp.json()["data"]["authorizationUrl"]
        assert "accounts.google.com" in url
        assert "hd=dome.tu.ac.th" in url
        assert "state=xyz123" in url


class TestTokenLifecycleAndCookies:
    """Secure Token Lifecycle with HTTP-Only Cookies and Refresh Endpoint (Issue #79)"""

    def test_login_sets_http_only_secure_samesite_cookies(self, db, client):
        """POST /api/auth/login sets HTTP-Only, SameSite cookies for access and refresh tokens"""
        user = User(
            id=uuid.uuid4(),
            email="sophia.dav@dome.tu.ac.th",
            name="Sophia Davis",
            student_id="6709616000",
            password_hash=hash_password("sophia6764"),
            role=UserRole.STUDENT,
        )
        db.add(user)
        db.commit()

        resp = client.post(
            "/api/auth/login",
            json={"username": "6709616000", "password": "sophia6764"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.cookies
        assert "refresh_token" in resp.cookies

        # Check Set-Cookie headers for security attributes
        cookie_headers = resp.headers.get_list("set-cookie")
        access_cookie_header = next(h for h in cookie_headers if "access_token=" in h)
        refresh_cookie_header = next(h for h in cookie_headers if "refresh_token=" in h)

        assert "httponly" in access_cookie_header.lower()
        assert "samesite=lax" in access_cookie_header.lower()
        assert "httponly" in refresh_cookie_header.lower()
        assert "samesite=lax" in refresh_cookie_header.lower()

    def test_sso_login_sets_cookies(self, db, client, fake_sso):
        """POST /api/auth/sso sets HTTP-Only, SameSite cookies for access and refresh tokens"""
        fake_sso.codes["tu-student-code"] = SSOUserInfo(
            email="freshman@dome.tu.ac.th",
            name="Freshman",
            email_verified=True,
            hd="dome.tu.ac.th",
        )
        resp = client.post("/api/auth/sso", json={"code": "tu-student-code"})
        assert resp.status_code == 200
        assert "access_token" in resp.cookies
        assert "refresh_token" in resp.cookies

    def test_refresh_token_extends_session_without_re_login(self, db, client):
        """POST /api/auth/refresh creates a new access token and refresh token via cookie or body"""
        user = User(
            id=uuid.uuid4(),
            email="sophia.dav@dome.tu.ac.th",
            name="Sophia Davis",
            role=UserRole.STUDENT,
        )
        db.add(user)
        db.commit()

        service = AuthService(db, UserRepository(db))
        _access, refresh_token = service.create_token_pair(user)

        # Test refresh via cookie
        client.cookies.set("refresh_token", refresh_token)
        resp = client.post("/api/auth/refresh")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        new_access = body["data"]["accessToken"]
        new_refresh = body["data"]["refreshToken"]

        assert new_access != refresh_token
        assert new_refresh is not None

        # Verify new access token works with protected endpoint
        me_resp = client.get("/api/me", headers={"Authorization": f"Bearer {new_access}"})
        assert me_resp.status_code == 200
        assert me_resp.json()["data"]["email"] == "sophia.dav@dome.tu.ac.th"

    def test_refresh_with_invalid_or_expired_token_returns_401(self, client):
        """Refreshing with invalid or expired refresh token returns 401"""
        resp_missing = client.post("/api/auth/refresh")
        assert resp_missing.status_code == 401
        assert resp_missing.json()["error"]["code"] == "invalid_token"

        resp_bad = client.post("/api/auth/refresh", json={"refreshToken": "not-a-valid-jwt"})
        assert resp_bad.status_code == 401
        assert resp_bad.json()["error"]["code"] == "invalid_token"

    def test_access_token_cannot_be_used_as_refresh_token(self, db, client):
        """An access token cannot be used to call the refresh endpoint"""
        user = User(
            id=uuid.uuid4(),
            email="sophia.dav@dome.tu.ac.th",
            name="Sophia Davis",
            role=UserRole.STUDENT,
        )
        db.add(user)
        db.commit()

        service = AuthService(db, UserRepository(db))
        access_token, _ = service.create_token_pair(user)

        resp = client.post("/api/auth/refresh", json={"refreshToken": access_token})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "invalid_token"

    def test_protected_route_without_token_returns_401(self, client):
        """Request without Authorization header or cookie returns 401 Unauthorized"""
        resp = client.get("/api/me")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "invalid_token"

    def test_protected_route_with_expired_token_returns_401(self, client):
        """Request with expired JWT returns 401 Unauthorized"""
        expired_token = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "type": "access",
                "exp": int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp()),
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        resp = client.get("/api/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "invalid_token"

    def test_protected_route_reads_http_only_cookie(self, db, client):
        """Request with valid access_token in HTTP-Only cookie succeeds on protected route"""
        user = User(
            id=uuid.uuid4(),
            email="sophia.dav@dome.tu.ac.th",
            name="Sophia Davis",
            role=UserRole.STUDENT,
        )
        db.add(user)
        db.commit()

        service = AuthService(db, UserRepository(db))
        access_token = service.create_access_token(user)

        client.cookies.set("access_token", access_token)
        resp = client.get("/api/me")
        assert resp.status_code == 200
        assert resp.json()["data"]["email"] == "sophia.dav@dome.tu.ac.th"

    def test_logout_clears_auth_cookies(self, client):
        """POST /api/auth/logout deletes access_token and refresh_token cookies"""
        client.cookies.set("access_token", "fake-token")
        client.cookies.set("refresh_token", "fake-refresh")

        resp = client.post("/api/auth/logout")
        assert resp.status_code == 200
        assert resp.json()["data"]["loggedOut"] is True

        cookie_headers = resp.headers.get_list("set-cookie")
        deleted_cookies = [h for h in cookie_headers if 'max-age=0' in h.lower() or 'expires=' in h.lower()]
        assert len(deleted_cookies) >= 2

