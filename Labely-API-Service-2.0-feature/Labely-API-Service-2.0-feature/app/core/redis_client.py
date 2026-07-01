# app/core/redis_client.py
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisClient:
    """Base Redis client with connection pooling"""

    def __init__(self):
        self._pool: Optional[redis.ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._initialized: bool = False

    async def initialize(self) -> bool:
        """Initialize Redis connection pool"""
        try:
            if not self._pool:
                self._pool = redis.ConnectionPool.from_url(
                    settings.REDIS_URL,
                    max_connections=settings.REDIS_MAX_CONNECTIONS,
                    decode_responses=True,
                    socket_keepalive=True,
                    health_check_interval=30
                )
                self._client = redis.Redis(connection_pool=self._pool)

                # Test connection
                await self._client.ping()
                self._initialized = True
                logger.info(f"Redis connection pool initialized (max_connections={settings.REDIS_MAX_CONNECTIONS})")
                return True
        except redis.ConnectionError as e:
            logger.error(f"Redis connection failed: {e}")
            self._initialized = False
            raise
        except Exception as e:
            logger.error(f"Redis initialization failed: {e}")
            self._initialized = False
            raise
        return False

    async def close(self):
        """Close Redis connections"""
        try:
            if self._pool:
                await self._pool.disconnect()
                self._pool = None
                self._client = None
                self._initialized = False
                logger.info("Redis connection pool closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")

    @property
    def client(self) -> redis.Redis:
        """Get Redis client"""
        if not self._client or not self._initialized:
            raise RuntimeError("Redis client not initialized. Call initialize() first.")
        return self._client

    @property
    def is_initialized(self) -> bool:
        """Check if Redis client is initialized"""
        return self._initialized

    def _serialize(self, data: Any) -> str:
        """Serialize data to JSON string"""
        try:
            return json.dumps(data, default=str)
        except (TypeError, ValueError) as e:
            logger.error(f"Serialization error: {e}")
            return str(data)

    def _deserialize(self, data: Optional[str]) -> Optional[Any]:
        """Deserialize JSON string to data"""
        if not data:
            return None

        # Try to parse as JSON first
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            # Return as string if not JSON
            return data
        except Exception as e:
            logger.debug(f"Deserialization error (returning raw data): {e}")
            return data

    @asynccontextmanager
    async def pipeline(self):
        """Get a Redis pipeline for atomic operations"""
        if not self.is_initialized:
            raise RuntimeError("Redis client not initialized")

        pipe = self.client.pipeline()
        try:
            yield pipe
            await pipe.execute()
        except Exception as e:
            await pipe.reset()
            logger.error(f"Pipeline error: {e}")
            raise e

    async def health_check(self) -> bool:
        """Check Redis connection health"""
        try:
            if self.is_initialized:
                return await self.client.ping()
            return False
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False

    async def get_info(self) -> Dict[str, Any]:
        """Get Redis server info"""
        try:
            if self.is_initialized:
                info = await self.client.info()
                return {
                    "version": info.get("redis_version", "unknown"),
                    "used_memory": info.get("used_memory_human", "unknown"),
                    "connected_clients": info.get("connected_clients", "unknown"),
                    "uptime_days": info.get("uptime_in_days", "unknown"),
                    "total_connections_received": info.get("total_connections_received", "unknown"),
                    "total_commands_processed": info.get("total_commands_processed", "unknown")
                }
            return {"error": "Redis not initialized"}
        except Exception as e:
            logger.error(f"Failed to get Redis info: {e}")
            return {"error": str(e)}

# Global Redis client instance
redis_client = RedisClient()

# Lifespan manager functions
async def init_redis():
    """Initialize Redis connections"""
    try:
        await redis_client.initialize()
        logger.info("Redis initialized")
        return True
    except Exception as e:
        logger.error(f"Redis initialization failed: {e}")
        # Don't raise - allow app to start even if Redis is down
        # But mark as not initialized
        return False

async def close_redis():
    """Close Redis connections"""
    try:
        await redis_client.close()
        logger.info("Redis closed")
    except Exception as e:
        logger.error(f"Error closing Redis: {e}")

# Helper function to get Redis client with lazy initialization
async def get_redis_client() -> RedisClient:
    """Get Redis client (initializes if needed)"""
    if not redis_client.is_initialized:
        await init_redis()
    return redis_client
