# app/core/redis_session.py
import hashlib
import logging
from datetime import datetime
from typing import List, Optional, Tuple

from app.core.config import settings

from .redis_client import redis_client

logger = logging.getLogger(__name__)

class RedisSessionManager:
    """Manage user sessions and rate limiting with Redis"""

    def __init__(self):
        self.SESSION_PREFIX = "session:"
        self.USER_SESSIONS_PREFIX = "user_sessions:"
        self.RATE_LIMIT_PREFIX = "rate_limit:"
        self.BLACKLIST_PREFIX = "blacklist:"

    async def create_session(self, user_id: int, token: str, device_info: str = None) -> bool:
        """Create a new user session"""
        try:
            session_id = hashlib.sha256(f"{user_id}:{token}".encode()).hexdigest()
            session_key = f"{self.SESSION_PREFIX}{session_id}"

            session_data = {
                "user_id": user_id,
                "token": token,
                "device_info": device_info,
                "created_at": datetime.utcnow().isoformat(),
                "last_activity": datetime.utcnow().isoformat()
            }

            # Store session with expiration
            await redis_client.client.setex(
                session_key,
                settings.REDIS_SESSION_TTL,
                redis_client._serialize(session_data)
            )

            # Add to user's session list
            user_key = f"{self.USER_SESSIONS_PREFIX}{user_id}"
            await redis_client.client.sadd(user_key, session_id)
            await redis_client.client.expire(user_key, settings.REDIS_SESSION_TTL)

            logger.debug(f"  Session created for user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            return False

    async def validate_session(self, token: str) -> Optional[dict]:
        """Validate a session token"""
        try:
            # Check if token is blacklisted
            if await self.is_blacklisted(token):
                return None

            # Find session by token (linear scan - for high volume, consider token->session mapping)
            pattern = f"{self.SESSION_PREFIX}*"
            async for key in redis_client.client.scan_iter(match=pattern):
                data = await redis_client.client.get(key)
                if data:
                    session = redis_client._deserialize(data)
                    if session and session.get("token") == token:
                        # Update last activity
                        session["last_activity"] = datetime.utcnow().isoformat()
                        await redis_client.client.setex(
                            key,
                            settings.REDIS_SESSION_TTL,
                            redis_client._serialize(session)
                        )
                        return session

            return None

        except Exception as e:
            logger.error(f"Failed to validate session: {e}")
            return None

    async def invalidate_session(self, token: str) -> bool:
        """Invalidate a specific session"""
        try:
            session = await self.validate_session(token)
            if session:
                # Blacklist the token
                await self.blacklist_token(token)

                # Remove from user's session list
                user_key = f"{self.USER_SESSIONS_PREFIX}{session['user_id']}"
                await redis_client.client.srem(user_key, token)

                logger.debug("  Session invalidated for token")
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to invalidate session: {e}")
            return False

    async def invalidate_all_user_sessions(self, user_id: int) -> int:
        """Invalidate all sessions for a user"""
        try:
            user_key = f"{self.USER_SESSIONS_PREFIX}{user_id}"
            session_ids = await redis_client.client.smembers(user_key)

            count = 0
            for session_id in session_ids:
                session_key = f"{self.SESSION_PREFIX}{session_id}"
                data = await redis_client.client.get(session_key)
                if data:
                    session = redis_client._deserialize(data)
                    if session:
                        await self.blacklist_token(session["token"])
                        await redis_client.client.delete(session_key)
                        count += 1

            await redis_client.client.delete(user_key)
            logger.info(f"  Invalidated {count} sessions for user {user_id}")
            return count

        except Exception as e:
            logger.error(f"Failed to invalidate user sessions: {e}")
            return 0

    async def blacklist_token(self, token: str, ttl: int = 86400) -> bool:
        """Add token to blacklist"""
        try:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            key = f"{self.BLACKLIST_PREFIX}{token_hash}"
            await redis_client.client.setex(key, ttl, "1")
            return True
        except Exception as e:
            logger.error(f"Failed to blacklist token: {e}")
            return False

    async def is_blacklisted(self, token: str) -> bool:
        """Check if token is blacklisted"""
        try:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            key = f"{self.BLACKLIST_PREFIX}{token_hash}"
            return await redis_client.client.exists(key) > 0
        except Exception as e:
            logger.error(f"Failed to check blacklist: {e}")
            return False

    async def check_rate_limit(self, key: str, limit: int, window: int) -> Tuple[bool, int, int]:
        """
        Check rate limit using sliding window
        Returns (allowed, current_count, ttl)
        """
        try:
            rate_key = f"{self.RATE_LIMIT_PREFIX}{key}"

            # Use pipeline for atomic operations
            pipe = redis_client.client.pipeline()
            pipe.incr(rate_key)
            pipe.ttl(rate_key)
            results = await pipe.execute()

            current_count = results[0]
            ttl = results[1]

            if ttl == -1:  # No expiration set
                await redis_client.client.expire(rate_key, window)
                ttl = window

            allowed = current_count <= limit
            return allowed, current_count, ttl

        except Exception as e:
            logger.error(f"Failed to check rate limit: {e}")
            return True, 0, window  # Allow on error

    async def get_user_active_sessions(self, user_id: int) -> List[dict]:
        """Get all active sessions for a user"""
        try:
            user_key = f"{self.USER_SESSIONS_PREFIX}{user_id}"
            session_ids = await redis_client.client.smembers(user_key)

            sessions = []
            for session_id in session_ids:
                session_key = f"{self.SESSION_PREFIX}{session_id}"
                data = await redis_client.client.get(session_key)
                if data:
                    session = redis_client._deserialize(data)
                    sessions.append(session)

            return sessions

        except Exception as e:
            logger.error(f"Failed to get user sessions: {e}")
            return []

# Global instance
redis_session = RedisSessionManager()
