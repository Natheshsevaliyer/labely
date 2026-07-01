import json
from typing import Any, Optional

import redis

from app.core.config import settings


class CacheService:
    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST or 'localhost',
            port=settings.REDIS_PORT or 6379,
            db=0,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=5
        )
        self.default_ttl = 300  # 5 minutes

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            value = self.redis_client.get(key)
            return json.loads(value) if value else None
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: int = None):
        """Set value in cache with TTL"""
        try:
            self.redis_client.setex(
                key,
                ttl or self.default_ttl,
                json.dumps(value, default=str)
            )
        except Exception:  # Instead of just "except:"
            return None

    def delete(self, key: str):
        """Delete from cache"""
        try:
            self.redis_client.delete(key)
        except Exception:  # Instead of just "except:"
            return None

    def invalidate_pattern(self, pattern: str):
        """Invalidate all keys matching pattern"""
        try:
            for key in self.redis_client.scan_iter(pattern):
                self.redis_client.delete(key)
        except Exception:  # Instead of just "except:"
            return None

cache_service = CacheService()
