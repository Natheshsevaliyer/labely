"""API dependencies."""
from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError
import logging
from fastapi import Request

from app.core.database import SessionLocal
from app.core.security import verify_token
from app.core.config import settings
from app.models.user import User
from app.core.exceptions import AuthenticationException
from app.core.redis_auth import redis_auth  # ← Import Redis manager
from app.core.redis_client import redis_client

logger = logging.getLogger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

def get_db() -> Generator:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(
    request: Request, # Inject the request object
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user from HttpOnly Cookie."""
    
    # 1. Extract token from Cookie instead of Header
    token = request.cookies.get(settings.COOKIE_NAME)
    
    if not token:
        logger.warning(f"Authentication failed: Token missing from cookies. Available cookies: {list(request.cookies.keys())}")
        raise AuthenticationException("Not authenticated. Token missing.")
    
    # 2. Check Redis Blacklist (as per your original code)
    is_blacklisted = await redis_auth.is_token_blacklisted(token)
    if is_blacklisted:
        logger.warning("Authentication failed: Token is blacklisted")
        raise AuthenticationException("Token has been revoked.")
    
    try:
        # 3. Verify JWT
        payload = verify_token(token)
        user_id = payload.get("sub")
        if not user_id:
            logger.warning("Authentication failed: Invalid token payload (no 'sub')")
            raise AuthenticationException("Invalid token")
    except Exception as e:
        logger.error(f"Authentication failed: JWT verification error: {str(e)}")
        raise AuthenticationException("Invalid token")
    
    # 4. Validate Redis Session (only if Redis initialized)
    try:
        if redis_client.is_initialized:
            session = await redis_auth.validate_session(token)
            if not session:
                logger.warning(f"Authentication failed: Session expired for user {user_id}")
                raise AuthenticationException("Session expired. Please login again.")
        else:
            # Redis not available — skip session validation but log a warning
            logger.warning("Redis not initialized — skipping session validation (dev mode)")
    except AuthenticationException:
        raise
    except Exception as e:
        logger.error(f"Error validating session: {e}", exc_info=True)
        raise AuthenticationException("Session validation failed")
    
    # 5. Get User from DB
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        logger.warning(f"Authentication failed: User {user_id} not found in database")
        raise AuthenticationException("User not found")
    
    logger.debug(f"Authentication successful for user {user_id}")
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current active user."""
    if not current_user.is_active:
        raise AuthenticationException("User is not active")
    return current_user