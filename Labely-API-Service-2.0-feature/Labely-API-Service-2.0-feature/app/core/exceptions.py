from typing import Any, Optional


class AppException(Exception):
    """Base application exception"""
    def __init__(self, message: str, status_code: int = 400, details: Optional[Any] = None):
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)

class NotFoundException(AppException):
    """Resource not found"""
    def __init__(self, message: str = "Resource not found", details: Optional[Any] = None):
        super().__init__(message, status_code=404, details=details)

class ValidationException(AppException):
    """Validation error"""
    def __init__(self, message: str = "Validation error", details: Optional[Any] = None):
        super().__init__(message, status_code=400, details=details)

class AuthenticationException(AppException):
    """Authentication error"""
    def __init__(self, message: str = "Authentication failed", details: Optional[Any] = None):
        super().__init__(message, status_code=401, details=details)

class AuthorizationException(AppException):
    """Authorization error"""
    def __init__(self, message: str = "Not authorized", details: Optional[Any] = None):
        super().__init__(message, status_code=403, details=details)

class ServiceUnavailableException(AppException):
    """External service unavailable"""
    def __init__(self, message: str = "Service unavailable", details: Optional[Any] = None):
        super().__init__(message, status_code=503, details=details)

class ConflictException(AppException):
    """Resource conflict"""
    def __init__(self, message: str = "Resource conflict", details: Optional[Any] = None):
        super().__init__(message, status_code=409, details=details)

class SRPServiceException(AppException):
    """SRP service specific errors"""
    def __init__(self, message: str = "SRP service error", details: Optional[Any] = None):
        super().__init__(message, status_code=503, details=details)

class MiraklAPIException(AppException):
    """Mirakl API specific errors"""
    def __init__(self, message: str = "Mirakl API error", details: Optional[Any] = None):
        super().__init__(message, status_code=502, details=details)

class DatabaseException(AppException):
    """Database operation errors"""
    def __init__(self, message: str = "Database error", details: Optional[Any] = None):
        super().__init__(message, status_code=500, details=details)
