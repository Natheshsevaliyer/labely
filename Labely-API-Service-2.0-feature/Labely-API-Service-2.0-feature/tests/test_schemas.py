"""Unit tests for Pydantic schemas."""
import pytest
from pydantic import ValidationError

from app.schemas.auth import (
    UserRegister,
    UserLogin,
    Token,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
    RefreshTokenRequest,
)
from app.schemas.order import GenerateLabelsRequest
from app.core.response import ApiResponse, ErrorResponse, PaginatedResponse


# ── Auth Schemas ─────────────────────────────────────────────────────────────

class TestUserRegister:
    def test_valid(self):
        u = UserRegister(email="user@example.com", username="john", password="secret1")
        assert u.email == "user@example.com"

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            UserRegister(email="not-an-email", username="john", password="secret1")

    def test_short_username(self):
        with pytest.raises(ValidationError):
            UserRegister(email="a@b.com", username="ab", password="secret1")

    def test_short_password(self):
        with pytest.raises(ValidationError):
            UserRegister(email="a@b.com", username="john", password="123")

    def test_max_username_length(self):
        with pytest.raises(ValidationError):
            UserRegister(email="a@b.com", username="x" * 51, password="secret1")


class TestUserLogin:
    def test_valid_login(self):
        u = UserLogin(email="a@b.com", password="mypassword")
        assert u.email == "a@b.com"

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            UserLogin(email="bad", password="pw")


class TestResetPasswordRequest:
    def test_matching_passwords(self):
        r = ResetPasswordRequest(token="tok", new_password="newpass1", confirm_password="newpass1")
        assert r.confirm_password == "newpass1"

    def test_mismatched_passwords_raise(self):
        with pytest.raises(ValidationError, match="Passwords do not match"):
            ResetPasswordRequest(token="tok", new_password="aaa111", confirm_password="bbb222")

    def test_short_new_password(self):
        with pytest.raises(ValidationError):
            ResetPasswordRequest(token="tok", new_password="123", confirm_password="123")


class TestChangePasswordRequest:
    def test_matching_passwords(self):
        r = ChangePasswordRequest(old_password="old", new_password="newpass1", confirm_password="newpass1")
        assert r.new_password == "newpass1"

    def test_mismatched_passwords_raise(self):
        with pytest.raises(ValidationError, match="Passwords do not match"):
            ChangePasswordRequest(old_password="old", new_password="aaa111", confirm_password="zzz999")


# ── Order Schemas ─────────────────────────────────────────────────────────────

class TestGenerateLabelsRequest:
    def test_quantity_only(self):
        r = GenerateLabelsRequest(srp="SRP", quantity=5)
        assert r.quantity == 5

    def test_date_range_only(self):
        r = GenerateLabelsRequest(srp="SRP", start_date="2024-01-01", end_date="2024-01-31")
        assert r.start_date == "2024-01-01"

    def test_order_id_with_label_count(self):
        r = GenerateLabelsRequest(srp="SRP", order_id="ORD-123", label_count=3)
        assert r.label_count == 3

    def test_no_method_raises(self):
        with pytest.raises(ValidationError, match="Either 'quantity'"):
            GenerateLabelsRequest(srp="SRP")

    def test_multiple_methods_raise(self):
        with pytest.raises(ValidationError, match="Cannot provide multiple methods"):
            GenerateLabelsRequest(srp="SRP", quantity=5, start_date="2024-01-01", end_date="2024-01-31")

    def test_only_order_id_without_label_count_raises(self):
        with pytest.raises(ValidationError):
            GenerateLabelsRequest(srp="SRP", order_id="ORD-123")

    def test_start_date_after_end_date_raises(self):
        with pytest.raises(ValidationError, match="start_date must be before"):
            GenerateLabelsRequest(srp="SRP", start_date="2024-02-01", end_date="2024-01-01")

    def test_invalid_date_format_raises(self):
        with pytest.raises(ValidationError):
            GenerateLabelsRequest(srp="SRP", start_date="01-01-2024", end_date="01-31-2024")

    def test_quantity_zero_raises(self):
        with pytest.raises(ValidationError):
            GenerateLabelsRequest(srp="SRP", quantity=0)

    def test_quantity_over_limit_raises(self):
        with pytest.raises(ValidationError):
            GenerateLabelsRequest(srp="SRP", quantity=101)

    def test_short_order_id_raises(self):
        with pytest.raises(ValidationError):
            GenerateLabelsRequest(srp="SRP", order_id="ab", label_count=2)


# ── Response Models ───────────────────────────────────────────────────────────

class TestApiResponse:
    def test_defaults(self):
        r = ApiResponse()
        assert r.success is True
        assert r.data is None

    def test_with_data(self):
        r = ApiResponse(data={"key": "value"}, message="ok")
        assert r.message == "ok"
        assert r.data == {"key": "value"}

    def test_error_response_defaults(self):
        r = ErrorResponse(error="Something failed")
        assert r.success is False
        assert r.error == "Something failed"


class TestPaginatedResponse:
    def test_paginated_response_fields(self):
        from app.core.response import PaginatedResponse as PR
        r = PR(items=[1, 2, 3], total=3, page=1, limit=10, pages=1, has_next=False, has_previous=False)
        assert len(r.items) == 3
        assert r.total == 3
