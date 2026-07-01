# app/core/redis_auth.py
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.core.config import settings

from .redis_client import redis_client, get_redis_client

logger = logging.getLogger(__name__)

class RedisAuthManager:
    """Redis manager for authentication and sessions"""

    def __init__(self):
        self.SESSION_PREFIX = "session:"
        self.USER_SESSIONS_PREFIX = "user_sessions:"
        self.TOKEN_BLACKLIST_PREFIX = "blacklist:"
        self.RATE_LIMIT_PREFIX = "rate_limit:"
        self.LOGIN_ATTEMPTS_PREFIX = "login_attempts:"
        self.SESSION_TTL = settings.REDIS_SESSION_TTL  # 8 hours

    def _hash_token(self, token: str) -> str:
        """Hash token for storage"""
        return hashlib.sha256(token.encode()).hexdigest()

    async def create_session(self, user_id: int, token: str, device_info: Optional[str] = None) -> bool:
        """Create a new user session"""
        try:
            session_id = self._hash_token(token)
            session_key = f"{self.SESSION_PREFIX}{session_id}"

            session_data = {
                "user_id": user_id,
                "token": token,
                "device_info": device_info,
                "created_at": datetime.utcnow().isoformat(),
                "last_activity": datetime.utcnow().isoformat()
            }

            rc = await get_redis_client()
            if not rc.is_initialized:
                logger.error("Redis client not initialized. Cannot create session.")
                return False

            # Store session
            await rc.client.setex(
                session_key,
                self.SESSION_TTL,
                rc._serialize(session_data)
            )

            # Add to user's session list
            user_key = f"{self.USER_SESSIONS_PREFIX}{user_id}"
            await rc.client.sadd(user_key, session_id)
            await rc.client.expire(user_key, self.SESSION_TTL)

            logger.info(f"Session created for user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            return False

    async def validate_session(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate a session token"""
        try:
            # Check blacklist first
            if await self.is_token_blacklisted(token):
                return None

            rc = await get_redis_client()
            if not rc.is_initialized:
                logger.error("Redis client not initialized. Cannot validate session.")
                return None

            session_id = self._hash_token(token)
            session_key = f"{self.SESSION_PREFIX}{session_id}"

            data = await rc.client.get(session_key)
            if data:
                session = rc._deserialize(data)
                # Update last activity
                session["last_activity"] = datetime.utcnow().isoformat()
                await rc.client.setex(
                    session_key,
                    self.SESSION_TTL,
                    rc._serialize(session)
                )
                return session

            return None

        except Exception as e:
            logger.error(f"Failed to validate session: {e}")
            return None

    async def invalidate_session(self, token: str) -> bool:
        """Invalidate a specific session"""
        try:
            rc = await get_redis_client()
            if not rc.is_initialized:
                logger.error("Redis client not initialized. Cannot invalidate session.")
                return False

            session_id = self._hash_token(token)
            session_key = f"{self.SESSION_PREFIX}{session_id}"

            # Get session data before deleting
            data = await rc.client.get(session_key)
            if data:
                session = rc._deserialize(data)
                user_id = session.get("user_id")

                # Remove from user's session list
                if user_id:
                    user_key = f"{self.USER_SESSIONS_PREFIX}{user_id}"
                    await rc.client.srem(user_key, session_id)

                # Blacklist the token
                await self.blacklist_token(token)

                # Delete session
                await rc.client.delete(session_key)
                logger.info(f"Session invalidated for user {user_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to invalidate session: {e}")
            return False

    async def invalidate_all_user_sessions(self, user_id: int) -> int:
        """Invalidate all sessions for a user"""
        try:
            rc = await get_redis_client()
            if not rc.is_initialized:
                logger.error("Redis client not initialized. Cannot invalidate user sessions.")
                return 0

            user_key = f"{self.USER_SESSIONS_PREFIX}{user_id}"
            session_ids = await rc.client.smembers(user_key)

            count = 0
            for session_id in session_ids:
                session_key = f"{self.SESSION_PREFIX}{session_id}"
                data = await rc.client.get(session_key)
                if data:
                    session = rc._deserialize(data)
                    token = session.get("token")
                    if token:
                        await self.blacklist_token(token)
                    await rc.client.delete(session_key)
                    count += 1

            await rc.client.delete(user_key)
            logger.info(f"Invalidated {count} sessions for user {user_id}")
            return count

        except Exception as e:
            logger.error(f"Failed to invalidate user sessions: {e}")
            return 0

    async def blacklist_token(self, token: str, ttl: int = 86400) -> bool:
        """Add token to blacklist (24 hours default)"""
        try:
            rc = await get_redis_client()
            if not rc.is_initialized:
                logger.error("Redis client not initialized. Cannot blacklist token.")
                return False

            token_hash = self._hash_token(token)
            key = f"{self.TOKEN_BLACKLIST_PREFIX}{token_hash}"
            await rc.client.setex(key, ttl, "1")
            return True
        except Exception as e:
            logger.error(f"Failed to blacklist token: {e}")
            return False

    async def is_token_blacklisted(self, token: str) -> bool:
        """Check if token is blacklisted"""
        try:
            rc = await get_redis_client()
            if not rc.is_initialized:
                logger.error("Redis client not initialized. Cannot check blacklist.")
                return False

            token_hash = self._hash_token(token)
            key = f"{self.TOKEN_BLACKLIST_PREFIX}{token_hash}"
            return await rc.client.exists(key) > 0
        except Exception as e:
            logger.error(f"Failed to check blacklist: {e}")
            return False

    async def check_rate_limit(self, identifier: str, limit: int = 60, window: int = 60) -> tuple[bool, int, int]:
        """
        Check rate limit for an identifier (IP, user_id, etc.)
        Returns: (allowed, current_count, ttl)
        """
        try:
            rc = await get_redis_client()
            if not rc.is_initialized:
                logger.error("Redis client not initialized. Allowing requests by default.")
                return True, 0, window

            key = f"{self.RATE_LIMIT_PREFIX}{identifier}"

            # Use pipeline for atomic operations
            pipe = rc.client.pipeline()
            pipe.incr(key)
            pipe.ttl(key)
            results = await pipe.execute()

            current_count = results[0]
            ttl = results[1]

            if ttl == -1:  # First request, set expiration
                await rc.client.expire(key, window)
                ttl = window

            allowed = current_count <= limit
            return allowed, current_count, ttl

        except Exception as e:
            logger.error(f"Failed to check rate limit: {e}")
            return True, 0, window  # Allow on error

    async def track_login_attempt(self, email: str, success: bool) -> Dict[str, Any]:
        """Track login attempts to detect brute force"""
        try:
            rc = await get_redis_client()
            if not rc.is_initialized:
                logger.error("Redis client not initialized. Skipping tracking login attempt.")
                return {"count": 0, "locked_until": None}

            key = f"{self.LOGIN_ATTEMPTS_PREFIX}{email}"

            # Get current attempts
            data = await rc.client.get(key)
            attempts = rc._deserialize(data) or {
                "count": 0,
                "last_attempt": None,
                "successful": 0,
                "failed": 0,
                "locked_until": None
            }

            # Update attempts
            now = datetime.utcnow()
            attempts["last_attempt"] = now.isoformat()
            attempts["count"] += 1

            if success:
                attempts["successful"] += 1
                # Reset lock on successful login
                attempts["locked_until"] = None
                attempts["failed"] = 0  # ← CRITICAL: Reset failed counter
                attempts["count"] = 0   # Optional: reset total count too

            else:
                attempts["failed"] += 1
                # Lock after 2 failed attempts
                if attempts["failed"] >= 2:
                    attempts["locked_until"] = (now + timedelta(minutes=2)).isoformat()

            # Store with 24 hour TTL
            await rc.client.setex(
                key,
                86400,
                rc._serialize(attempts)
            )

            return attempts

        except Exception as e:
            logger.error(f"Failed to track login attempt: {e}")
            return {"count": 0, "locked_until": None}

    async def is_login_locked(self, email: str) -> tuple[bool, Optional[int]]:
        """Check if login is locked due to too many failures
        Returns: (is_locked, remaining_minutes)
        """
        try:
            rc = await get_redis_client()
            if not rc.is_initialized:
                logger.error("Redis client not initialized. Cannot check login lock.")
                return False, None

            key = f"{self.LOGIN_ATTEMPTS_PREFIX}{email}"
            data = await rc.client.get(key)

            if data:
                attempts = rc._deserialize(data)
                locked_until = attempts.get("locked_until")

                if locked_until:
                    locked_until_dt = datetime.fromisoformat(locked_until)
                    now = datetime.utcnow()

                    if locked_until_dt > now:
                        # Still locked
                        remaining_seconds = int((locked_until_dt - now).total_seconds())
                        remaining_minutes = max(1, (remaining_seconds + 59) // 60)
                        return True, remaining_minutes
                    else:
                        # Lock has expired - reset the failed counter automatically
                        attempts["locked_until"] = None
                        attempts["failed"] = 0
                        attempts["count"] = 0
                        await rc.client.setex(
                            key,
                            86400,
                            rc._serialize(attempts)
                        )
                        logger.info(f"Login lock expired for {email}, resetting failed attempts")

            return False, None

        except Exception as e:
            logger.error(f"Failed to check login lock: {e}")
            return False, None

    async def get_user_active_sessions(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all active sessions for a user"""
        try:
            rc = await get_redis_client()
            if not rc.is_initialized:
                logger.error("Redis client not initialized. Cannot get user sessions.")
                return []

            user_key = f"{self.USER_SESSIONS_PREFIX}{user_id}"
            session_ids = await rc.client.smembers(user_key)

            sessions = []
            for session_id in session_ids:
                session_key = f"{self.SESSION_PREFIX}{session_id}"
                data = await rc.client.get(session_key)
                if data:
                    session = rc._deserialize(data)
                    sessions.append(session)

            return sessions

        except Exception as e:
            logger.error(f"Failed to get user sessions: {e}")
            return []

# Global instance
redis_auth = RedisAuthManager()
