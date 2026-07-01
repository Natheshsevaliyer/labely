# app/services/auth_service.py
import asyncio
import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthenticationException, NotFoundException, ValidationException
from app.core.redis_auth import redis_auth
from app.core.security import create_access_token
from app.models.token import RefreshToken
from app.models.user import PasswordResetToken, User
from app.schemas.auth import UserLogin, UserRegister
from app.services.base import BaseService
from app.services.email_service import email_service

logger = logging.getLogger(__name__)

class AuthService(BaseService[User]):
    """Authentication service with Redis session management."""

    def __init__(self, db: Session):
        super().__init__(User, db)

    async def register(self, user_data: UserRegister, request: Request = None) -> User:
        """Register a new user."""
        existing = self.db.query(User).filter(
            (User.email == user_data.email) | (User.username == user_data.username)
        ).first()

        if existing:
            raise ValidationException("Email or username already registered")

        user = User(
            email=user_data.email,
            username=user_data.username
        )
        user.set_password(user_data.password)

        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        logger.info(f"  New user registered: {user.email}")
        return user

    async def login(self, user_data: UserLogin, request: Request = None) -> Dict[str, Any]:
        """Login user with Redis session tracking."""

        # Check if login is locked due to too many failures
        is_locked, remaining_minutes = await redis_auth.is_login_locked(user_data.email)
        if is_locked:
            if remaining_minutes:
                raise AuthenticationException(
                    f"Account temporarily locked. Too many failed attempts. "
                    f"Please try again in {remaining_minutes} minute(s)."
                )
            else:
                raise AuthenticationException(
                    "Account temporarily locked due to too many failed attempts."
                )

        # Get client IP for rate limiting
        client_ip = request.client.host if request else "unknown"

        # Check rate limit for this IP
        allowed, count, ttl = await redis_auth.check_rate_limit(
            f"login_ip:{client_ip}",
            limit=10,
            window=60
        )

        if not allowed:
            logger.warning(f"Rate limit exceeded for IP {client_ip}")
            raise AuthenticationException("Too many login attempts. Please try again later.")

        # Find user
        user = self.db.query(User).filter(User.email == user_data.email).first()

        # Verify password
        password_valid = user and user.verify_password(user_data.password)

        # Track login attempt (this will reset failed counter on success)
        await redis_auth.track_login_attempt(user_data.email, password_valid)

        if not user or not password_valid:
            raise AuthenticationException("Invalid credentials")

        # If we get here, login is successful
        # Create access token
        access_token = create_access_token(
            data={"sub": str(user.id)},
            expires_delta=timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
        )

        # Create refresh token
        refresh_token = self.create_refresh_token(user.id, "web")

        # Create Redis session
        device_info = request.headers.get("user-agent", "unknown") if request else "unknown"
        await redis_auth.create_session(
            user_id=user.id,
            token=access_token,
            device_info=device_info
        )

        logger.info(f"User logged in: {user.email} from {client_ip}")

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "username": user.username,
            "email": user.email,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "message": "Login successful"
        }

    async def logout(self, token: str) -> bool:
        """Logout user - invalidate session"""
        return await redis_auth.invalidate_session(token)

    async def logout_all_devices(self, user_id: int) -> int:
        """Logout from all devices - revokes ALL tokens"""
        # Revoke all refresh tokens
        self.db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked == False
        ).update({"revoked": True})
        self.db.commit()
        
        # Revoke all Redis sessions
        return await redis_auth.invalidate_all_user_sessions(user_id)

    async def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate token and return session data"""
        return await redis_auth.validate_session(token)

    async def get_active_sessions(self, user_id: int) -> list:
        """Get all active sessions for a user"""
        return await redis_auth.get_user_active_sessions(user_id)

    def create_refresh_token(self, user_id: int, device_info: str = None) -> str:
        """Create a refresh token"""
        token = secrets.token_urlsafe(64)
        expires_at = datetime.utcnow() + timedelta(days=30)

        refresh_token = RefreshToken(
            user_id=user_id,
            token=token,
            expires_at=expires_at,
            device_info=device_info
        )
        self.db.add(refresh_token)
        self.db.commit()

        return token

    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Get new access token using refresh token"""
        token = self.db.query(RefreshToken).filter(
            RefreshToken.token == refresh_token,
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.utcnow()
        ).first()

        if not token:
            raise AuthenticationException("Invalid or expired refresh token")

        # Create new access token
        access_token = create_access_token(
            data={"sub": str(token.user_id)},
            expires_delta=timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
        )

        return {
            "access_token": access_token,
            "token_type": "bearer"
        }

    def revoke_refresh_token(self, refresh_token: str, user_id: int = None) -> bool:
        """
        Revoke a refresh token (logout)
        Returns True if revoked, False if token not found or doesn't belong to user
        """
        query = self.db.query(RefreshToken).filter(
            RefreshToken.token == refresh_token,
            RefreshToken.revoked == False
        )
        
        # If user_id provided, ensure token belongs to this user
        if user_id is not None:
            query = query.filter(RefreshToken.user_id == user_id)
        
        token = query.first()
        
        if not token:
            logger.warning(f"Failed to revoke refresh token: token not found or belongs to different user")
            return False
        
        token.revoked = True
        self.db.commit()
        logger.info(f"Refresh token revoked for user {token.user_id}")
        return True

    async def forgot_password(self, email: str, background_tasks: BackgroundTasks) -> Dict[str, Any]:
        """Request password reset."""
        user = self.db.query(User).filter(User.email == email).first()

        # Always return success for security
        if not user:
            return {
                "message": "If an account exists with this email, a password reset link has been sent.",
                "success": True
            }

        # Generate token
        token = secrets.token_urlsafe(32)
        hashed_token = hashlib.sha256(token.encode()).hexdigest()

        reset_token = PasswordResetToken(
            user_id=user.id,
            token=hashed_token,
            expires_at=datetime.utcnow() + timedelta(hours=1),
            used=False
        )

        self.db.add(reset_token)
        self.db.commit()

        # Send email in background
        background_tasks.add_task(
            email_service.send_password_reset_email,
            user.email,
            token,
            user.username
        )

        return {
            "message": "If an account exists with this email, a password reset link has been sent.",
            "success": True
        }

    def reset_password(self, token: str, new_password: str) -> Dict[str, Any]:
        """Reset password using token."""
        hashed_token = hashlib.sha256(token.encode()).hexdigest()

        reset_token = self.db.query(PasswordResetToken).filter(
            PasswordResetToken.token == hashed_token,
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > datetime.utcnow()
        ).first()

        if not reset_token:
            raise ValidationException("Invalid or expired reset token")

        user = self.db.query(User).filter(User.id == reset_token.user_id).first()
        if not user:
            raise NotFoundException("User not found")

        user.set_password(new_password)
        reset_token.used = True
        reset_token.expires_at = datetime.utcnow()

        self.db.commit()

        # Invalidate all sessions for this user (force re-login)
        asyncio.create_task(self.logout_all_devices(user.id))

        return {
            "message": "Password has been reset successfully.",
            "success": True
        }

    def change_password(self, user_id: int, old_password: str, new_password: str) -> Dict[str, Any]:
        """Change password for authenticated user."""
        user = self.get_or_404(user_id)

        if not user.verify_password(old_password):
            raise ValidationException("Current password is incorrect")

        if old_password == new_password:
            raise ValidationException("New password must be different from current password")

        user.set_password(new_password)
        self.db.commit()

        return {
            "message": "Password has been changed successfully.",
            "success": True
        }
