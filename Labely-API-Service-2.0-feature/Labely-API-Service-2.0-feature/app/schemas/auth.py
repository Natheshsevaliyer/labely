from datetime import datetime
from typing import Optional

from pydantic import EmailStr, Field, validator

from .base import BaseSchema


class UserRegister(BaseSchema):
    """User registration schema."""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)

class UserLogin(BaseSchema):
    """User login schema."""
    email: EmailStr
    password: str

class Token(BaseSchema):
    """Token response schema."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    message: Optional[str] = None

class UserResponse(BaseSchema):
    """User response schema."""
    id: int
    email: str
    username: str
    created_at: datetime
    updated_at: datetime

class ForgotPasswordRequest(BaseSchema):
    """Forgot password request schema."""
    email: EmailStr

class ResetPasswordRequest(BaseSchema):
    """Reset password request schema."""
    token: str
    new_password: str = Field(..., min_length=6)
    confirm_password: str

    @validator('confirm_password')
    def passwords_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Passwords do not match')
        return v

class ChangePasswordRequest(BaseSchema):
    """Change password request schema."""
    old_password: str
    new_password: str = Field(..., min_length=6)
    confirm_password: str

    @validator('confirm_password')
    def passwords_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Passwords do not match')
        return v

class MessageResponse(BaseSchema):
    """Message response schema."""
    message: str
    success: bool = True

class RefreshTokenRequest(BaseSchema):
    # This can now be empty or optional because the token is in the cookie
    refresh_token: Optional[str] = None