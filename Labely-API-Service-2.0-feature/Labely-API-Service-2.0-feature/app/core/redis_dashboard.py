# app/core/redis_dashboard.py
import logging
from typing import Any, Dict, Optional

from .redis_client import redis_client

logger = logging.getLogger(__name__)

class RedisDashboardCache:
    """Redis caching specifically for dashboard data"""

    def __init__(self):
        self.DASHBOARD_PREFIX = "dashboard:user:"
        self.CHART_PREFIX = "dashboard:charts:user:"
        self.STATS_PREFIX = "dashboard:stats:user:"
        self.DEFAULT_TTL = 300  # 5 minutes

    async def cache_dashboard(self, user_id: int, data: Dict[str, Any]) -> bool:
        """Cache full dashboard data"""
        try:
            key = f"{self.DASHBOARD_PREFIX}{user_id}"
            await redis_client.client.setex(
                key,
                self.DEFAULT_TTL,
                redis_client._serialize(data)
            )
            logger.debug(f"Dashboard cached for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cache dashboard: {e}")
            return False

    async def get_cached_dashboard(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get cached dashboard data"""
        try:
            key = f"{self.DASHBOARD_PREFIX}{user_id}"
            data = await redis_client.client.get(key)
            if data:
                logger.debug(f"Dashboard cache hit for user {user_id}")
                return redis_client._deserialize(data)
            logger.debug(f"Dashboard cache miss for user {user_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to get cached dashboard: {e}")
            return None

    async def invalidate_dashboard(self, user_id: int):
        """Invalidate dashboard cache when new data is generated"""
        try:
            key = f"{self.DASHBOARD_PREFIX}{user_id}"
            await redis_client.client.delete(key)
            logger.debug(f"Dashboard cache invalidated for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to invalidate dashboard: {e}")

    async def cache_chart_data(self, user_id: int, chart_type: str, data: Dict[str, Any]):
        """Cache specific chart data"""
        try:
            key = f"{self.CHART_PREFIX}{user_id}:{chart_type}"
            await redis_client.client.setex(
                key,
                self.DEFAULT_TTL,
                redis_client._serialize(data)
            )
        except Exception as e:
            logger.error(f"Failed to cache chart data: {e}")

    async def get_cached_chart(self, user_id: int, chart_type: str) -> Optional[Dict[str, Any]]:
        """Get cached chart data"""
        try:
            key = f"{self.CHART_PREFIX}{user_id}:{chart_type}"
            data = await redis_client.client.get(key)
            return redis_client._deserialize(data) if data else None
        except Exception as e:
            logger.error(f"Failed to get cached chart: {e}")
            return None

# Global instance
redis_dashboard = RedisDashboardCache()
