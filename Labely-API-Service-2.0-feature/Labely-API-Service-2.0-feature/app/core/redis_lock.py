# app/core/redis_lock.py
import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Callable, Optional

from app.core.config import settings

from .redis_client import redis_client

logger = logging.getLogger(__name__)

class RedisLock:
    """Distributed lock using Redis with auto-renewal"""

    def __init__(self):
        self.LOCK_PREFIX = "lock:"
        self.default_timeout = settings.REDIS_LOCK_TIMEOUT
        self.auto_renewal = True
        self.renewal_interval = self.default_timeout / 3  # Renew at 1/3 of timeout

    async def acquire(self, lock_name: str, timeout: Optional[int] = None,
                      blocking: bool = True, blocking_timeout: Optional[int] = None) -> Optional[str]:
        """
        Acquire a distributed lock
        Args:
            lock_name: Name of the lock
            timeout: Lock expiration in seconds
            blocking: Whether to block until lock is acquired
            blocking_timeout: Maximum time to block
        Returns:
            Lock token if acquired, None otherwise
        """
        lock_key = f"{self.LOCK_PREFIX}{lock_name}"
        lock_value = str(uuid.uuid4())
        expire = timeout or self.default_timeout

        start_time = time.time()

        while True:
            # Try to acquire lock with NX (only set if not exists)
            acquired = await redis_client.client.set(
                lock_key,
                lock_value,
                nx=True,
                ex=expire
            )

            if acquired:
                logger.debug(f"  Lock acquired: {lock_name} (token: {lock_value})")

                # Start auto-renewal if enabled
                if self.auto_renewal:
                    asyncio.create_task(self._auto_renew(lock_name, lock_value, expire))

                return lock_value

            if not blocking:
                return None

            # Check if we've exceeded blocking timeout
            if blocking_timeout and (time.time() - start_time) > blocking_timeout:
                return None

            # Wait before retrying
            await asyncio.sleep(0.1)

    async def release(self, lock_name: str, lock_value: str) -> bool:
        """
        Release the lock only if we own it
        Args:
            lock_name: Name of the lock
            lock_value: Token received from acquire()
        Returns:
            True if released, False otherwise
        """
        lock_key = f"{self.LOCK_PREFIX}{lock_name}"

        # Lua script to ensure atomic release
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        try:
            result = await redis_client.client.eval(lua_script, 1, lock_key, lock_value)
            if result == 1:
                logger.debug(f"Lock released: {lock_name}")
                return True
            else:
                logger.warning(f" Failed to release lock {lock_name} - not owner or already expired")
                return False

        except Exception as e:
            logger.error(f"Error releasing lock {lock_name}: {e}")
            return False

    async def _auto_renew(self, lock_name: str, lock_value: str, expire: int):
        """Auto-renew lock periodically"""
        try:
            while True:
                await asyncio.sleep(self.renewal_interval)

                lock_key = f"{self.LOCK_PREFIX}{lock_name}"

                # Lua script to renew lock if we still own it
                lua_script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("expire", KEYS[1], ARGV[2])
                else
                    return 0
                end
                """

                result = await redis_client.client.eval(
                    lua_script,
                    1,
                    lock_key,
                    lock_value,
                    expire
                )

                if result == 1:
                    logger.debug(f"Lock renewed: {lock_name}")
                else:
                    logger.warning(f"Lock lost: {lock_name}")
                    break

        except asyncio.CancelledError:
            logger.debug(f"Lock renewal cancelled: {lock_name}")
        except Exception as e:
            logger.error(f"Error renewing lock {lock_name}: {e}")

    @asynccontextmanager
    async def lock(self, lock_name: str, timeout: Optional[int] = None,
                   blocking: bool = True, blocking_timeout: Optional[int] = None):
        """
        Context manager for distributed lock
        Usage:
            async with redis_lock.lock("my_lock"):
                # critical section
        """
        lock_value = await self.acquire(lock_name, timeout, blocking, blocking_timeout)

        if not lock_value:
            raise TimeoutError(f"Could not acquire lock: {lock_name}")

        try:
            yield lock_value
        finally:
            await self.release(lock_name, lock_value)

    async def execute_with_lock(self, lock_name: str, func: Callable, *args, **kwargs):
        """Execute function with distributed lock"""
        async with self.lock(lock_name):
            return await func(*args, **kwargs)

# Global instance
redis_lock = RedisLock()
