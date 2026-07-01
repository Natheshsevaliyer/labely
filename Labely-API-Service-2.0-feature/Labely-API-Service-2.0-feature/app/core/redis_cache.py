# app/core/redis_cache.py
import hashlib
import logging
from functools import wraps
from typing import Any, Callable, Optional

from .redis_client import redis_client

logger = logging.getLogger(__name__)

class RedisCache:
    """Enhanced caching with versioning and invalidation patterns"""

    def __init__(self):
        self.CACHE_PREFIX = "cache:"
        self.VERSION_PREFIX = "cache_version:"
        self.TAG_PREFIX = "cache_tag:"
        self.default_ttl = 300  # 5 minutes

    def _make_key(self, key: str, version: Optional[str] = None) -> str:
        """Create cache key with optional version"""
        if version:
            return f"{self.CACHE_PREFIX}{version}:{key}"
        return f"{self.CACHE_PREFIX}{key}"

    def _make_tag_key(self, tag: str) -> str:
        """Create tag key for cache invalidation"""
        return f"{self.TAG_PREFIX}{tag}"

    async def get(self, key: str, version: Optional[str] = None) -> Optional[Any]:
        """Get value from cache"""
        try:
            cache_key = self._make_key(key, version)
            data = await redis_client.client.get(cache_key)

            if data:
                logger.debug(f"Cache hit: {key}")
                return redis_client._deserialize(data)

            logger.debug(f"Cache miss: {key}")
            return None

        except Exception as e:
            logger.error(f"Cache get error for {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None,
                  tags: Optional[list] = None, version: Optional[str] = None):
        """Set value in cache with optional tags for invalidation"""
        try:
            cache_key = self._make_key(key, version)
            ttl = ttl or self.default_ttl

            # Store the value
            await redis_client.client.setex(
                cache_key,
                ttl,
                redis_client._serialize(value)
            )

            # Add tags for invalidation
            if tags:
                pipe = redis_client.client.pipeline()
                for tag in tags:
                    tag_key = self._make_tag_key(tag)
                    pipe.sadd(tag_key, cache_key)
                    pipe.expire(tag_key, ttl)
                await pipe.execute()

            logger.debug(f"Cache set: {key} (ttl={ttl})")

        except Exception as e:
            logger.error(f"Cache set error for {key}: {e}")

    async def delete(self, key: str, version: Optional[str] = None):
        """Delete specific cache key"""
        try:
            cache_key = self._make_key(key, version)
            await redis_client.client.delete(cache_key)
            logger.debug(f"Cache deleted: {key}")

        except Exception as e:
            logger.error(f"Cache delete error for {key}: {e}")

    async def invalidate_by_tag(self, tag: str):
        """Invalidate all cache entries with a specific tag"""
        try:
            tag_key = self._make_tag_key(tag)
            cache_keys = await redis_client.client.smembers(tag_key)

            if cache_keys:
                # Delete all associated cache keys
                pipe = redis_client.client.pipeline()
                for cache_key in cache_keys:
                    pipe.delete(cache_key)
                pipe.delete(tag_key)
                await pipe.execute()

                logger.info(f"Invalidated {len(cache_keys)} cache entries with tag: {tag}")

        except Exception as e:
            logger.error(f"Cache invalidation error for tag {tag}: {e}")

    async def increment_version(self, namespace: str) -> str:
        """Increment version for a namespace (for cache busting)"""
        try:
            version_key = f"{self.VERSION_PREFIX}{namespace}"
            version = await redis_client.client.incr(version_key)

            # Set expiration for version key (30 days)
            await redis_client.client.expire(version_key, 86400 * 30)

            return str(version)

        except Exception as e:
            logger.error(f"Failed to increment version for {namespace}: {e}")
            return "1"

    async def get_version(self, namespace: str) -> str:
        """Get current version for a namespace"""
        try:
            version_key = f"{self.VERSION_PREFIX}{namespace}"
            version = await redis_client.client.get(version_key)
            return version or "1"

        except Exception as e:
            logger.error(f"Failed to get version for {namespace}: {e}")
            return "1"

    def cached(self, ttl: Optional[int] = None, tags: Optional[list] = None,
               key_builder: Optional[Callable] = None, version_namespace: Optional[str] = None):
        """
        Decorator for caching function results
        Usage:
            @cache.cached(ttl=300, tags=["users"])
            async def get_user(user_id: int):
                return await fetch_user(user_id)
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Build cache key
                if key_builder:
                    cache_key = key_builder(*args, **kwargs)
                else:
                    # Default key builder using function name and arguments
                    args_str = ":".join(str(arg) for arg in args)
                    kwargs_str = ":".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
                    cache_key = f"{func.__name__}:{args_str}:{kwargs_str}"
                    cache_key = hashlib.md5(cache_key.encode()).hexdigest()

                # Get version if namespace provided
                version = None
                if version_namespace:
                    version = await self.get_version(version_namespace)

                # Try to get from cache
                cached_value = await self.get(cache_key, version)
                if cached_value is not None:
                    return cached_value

                # Execute function
                result = await func(*args, **kwargs)

                # Cache result
                await self.set(cache_key, result, ttl, tags, version)

                return result

            return wrapper
        return decorator

# Global instance
redis_cache = RedisCache()
