"""Unit tests for app/core/exceptions.py"""
import pytest

from app.core.exceptions import (
    AppException,
    NotFoundException,
    ValidationException,
    AuthenticationException,
    AuthorizationException,
    ServiceUnavailableException,
    ConflictException,
    SRPServiceException,
    MiraklAPIException,
    DatabaseException,
)


class TestAppException:
    def test_default_status_code(self):
        exc = AppException("something went wrong")
        assert exc.status_code == 400
        assert exc.message == "something went wrong"
        assert exc.details is None

    def test_custom_status_and_details(self):
        exc = AppException("err", status_code=500, details={"key": "val"})
        assert exc.status_code == 500
        assert exc.details == {"key": "val"}

    def test_is_exception(self):
        exc = AppException("boom")
        assert isinstance(exc, Exception)


class TestSubclassedExceptions:
    @pytest.mark.parametrize("exc_class,expected_code", [
        (NotFoundException, 404),
        (ValidationException, 400),
        (AuthenticationException, 401),
        (AuthorizationException, 403),
        (ServiceUnavailableException, 503),
        (ConflictException, 409),
        (SRPServiceException, 503),
        (MiraklAPIException, 502),
        (DatabaseException, 500),
    ])
    def test_default_status_codes(self, exc_class, expected_code):
        exc = exc_class()
        assert exc.status_code == expected_code

    def test_not_found_custom_message(self):
        exc = NotFoundException("Order 42 not found")
        assert exc.message == "Order 42 not found"
        assert exc.status_code == 404

    def test_validation_exception_details(self):
        exc = ValidationException("bad input", details=["field x is required"])
        assert exc.details == ["field x is required"]

    def test_auth_exception_inherits_app_exception(self):
        exc = AuthenticationException()
        assert isinstance(exc, AppException)
