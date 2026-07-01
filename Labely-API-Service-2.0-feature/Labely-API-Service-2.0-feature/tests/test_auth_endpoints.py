"""Integration tests for /api/v1/auth/* endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.user import User
from app.core.security import hash_password, create_access_token


# Helper -----------------------------------------------------------------

def _register_payload(email="new@example.com", username="newuser", password="password123"):
    return {"email": email, "username": username, "password": password}


# ── Register ─────────────────────────────────────────────────────────────────

class TestRegisterEndpoint:
    def test_register_success(self, client, db):
        from datetime import datetime
        with patch("app.services.auth_service.AuthService.register", new_callable=AsyncMock) as mock_reg:
            mock_user = MagicMock()
            mock_user.id = 99
            mock_user.email = "new@example.com"
            mock_user.username = "newuser"
            mock_user.created_at = datetime.utcnow()
            mock_user.updated_at = datetime.utcnow()
            mock_user.model_fields = {}
            mock_reg.return_value = mock_user

            with patch("app.api.v1.endpoints.auth.UserResponse.model_validate") as mock_validate:
                from app.schemas.auth import UserResponse
                from datetime import datetime as dt
                mock_validate.return_value = UserResponse(
                    id=99, email="new@example.com", username="newuser",
                    created_at=dt.utcnow(), updated_at=dt.utcnow()
                )
                resp = client.post("/api/v1/auth/register", json=_register_payload())
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is True

    def test_register_invalid_email(self, client):
        resp = client.post("/api/v1/auth/register", json=_register_payload(email="not-email"))
        assert resp.status_code == 422

    def test_register_short_password(self, client):
        resp = client.post("/api/v1/auth/register", json=_register_payload(password="123"))
        assert resp.status_code == 422

    def test_register_short_username(self, client):
        resp = client.post("/api/v1/auth/register", json=_register_payload(username="ab"))
        assert resp.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────

class TestLoginEndpoint:
    def test_login_success(self, client, test_user):
        with patch("app.services.auth_service.AuthService.login", new_callable=AsyncMock) as mock_login:
            mock_login.return_value = {
                "access_token": "tok",
                "refresh_token": "ref",
                "token_type": "bearer",
                "message": "Login successful",
            }
            resp = client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["data"]["access_token"] == "tok"

    def test_login_missing_fields(self, client):
        resp = client.post("/api/v1/auth/login", json={"email": "a@b.com"})
        assert resp.status_code == 422


# ── /me ───────────────────────────────────────────────────────────────────────

class TestMeEndpoint:
    def test_me_returns_user_info(self, authed_client, test_user):
        resp = authed_client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["email"] == test_user.email
        assert data["data"]["username"] == test_user.username

    def test_me_requires_auth(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401


# ── Forgot / Reset password ───────────────────────────────────────────────────

class TestForgotPassword:
    def test_forgot_password_valid_email(self, client):
        with patch("app.services.auth_service.AuthService.forgot_password", new_callable=AsyncMock) as m:
            m.return_value = {"message": "Reset link sent", "success": True}
            resp = client.post("/api/v1/auth/forgot-password", json={"email": "a@example.com"})
            assert resp.status_code == 200

    def test_forgot_password_invalid_email(self, client):
        resp = client.post("/api/v1/auth/forgot-password", json={"email": "not-email"})
        assert resp.status_code == 422


class TestResetPassword:
    def test_reset_password_success(self, client):
        with patch("app.services.auth_service.AuthService.reset_password") as m:
            m.return_value = {"message": "Password reset successful", "success": True}
            resp = client.post("/api/v1/auth/reset-password", json={
                "token": "valid-token",
                "new_password": "newpass1",
                "confirm_password": "newpass1",
            })
            assert resp.status_code == 200

    def test_reset_password_mismatch(self, client):
        resp = client.post("/api/v1/auth/reset-password", json={
            "token": "tok",
            "new_password": "aaa111",
            "confirm_password": "bbb222",
        })
        assert resp.status_code == 422


# ── Refresh token ─────────────────────────────────────────────────────────────

class TestRefreshToken:
    def test_refresh_success(self, client):
        with patch("app.services.auth_service.AuthService.refresh_access_token") as m:
            m.return_value = {"access_token": "new-tok", "token_type": "bearer"}
            resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "some-refresh-token"})
            assert resp.status_code == 200

    def test_refresh_missing_token(self, client):
        resp = client.post("/api/v1/auth/refresh", json={})
        assert resp.status_code == 422
