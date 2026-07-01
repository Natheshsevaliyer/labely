# app/core/redis_process.py
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .redis_client import redis_client

logger = logging.getLogger(__name__)

class RedisProcessTracker:
    """Track label generation processes in Redis"""

    def __init__(self):
        self.PROCESS_PREFIX = "process:"
        self.USER_PROCESSES_PREFIX = "user_processes:"
        self.PROCESS_STATS_PREFIX = "process_stats:"
        self.PROCESS_TTL = 86400  # 24 hours

    async def create_process(self, process_id: int, user_id: int, data: Dict[str, Any]) -> bool:
        """Create a new process tracking entry"""
        try:
            key = f"{self.PROCESS_PREFIX}{process_id}"

            process_data = {
                "process_id": process_id,
                "user_id": user_id,
                "status": data.get("status", "pending"),
                "total": data.get("total", 0),
                "processed": data.get("processed", 0),
                "successful": data.get("successful", 0),
                "failed": data.get("failed", 0),
                "srp": data.get("srp", ""),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "completed_at": None,
                "download_url": None,
                "labels_only_url": None,
                "report_url": None
            }

            # Store process data
            await redis_client.client.setex(
                key,
                self.PROCESS_TTL,
                redis_client._serialize(process_data)
            )

            # Add to user's process list
            user_key = f"{self.USER_PROCESSES_PREFIX}{user_id}"
            await redis_client.client.zadd(
                user_key,
                {str(process_id): datetime.utcnow().timestamp()}
            )
            await redis_client.client.expire(user_key, self.PROCESS_TTL)

            logger.info(f"  Process {process_id} tracking created in Redis")
            return True

        except Exception as e:
            logger.error(f"Failed to create process tracking: {e}")
            return False

    # app/core/redis_process.py - Ensure update_process preserves URLs

    async def update_process(self, process_id: int, updates: Dict[str, Any]) -> bool:
        """Update process status"""
        try:
            key = f"{self.PROCESS_PREFIX}{process_id}"

            # Get current data
            data = await redis_client.client.get(key)
            if not data:
                logger.warning(f"Process {process_id} not found in Redis")
                return False

            process_data = redis_client._deserialize(data)
            process_data.update(updates)
            process_data["updated_at"] = datetime.utcnow().isoformat()

            # If status is completed/failed/partial, set completed_at
            if updates.get("status") in ["Completed", "Failed", "Partial"]:
                process_data["completed_at"] = datetime.utcnow().isoformat()

            # Store updated data
            await redis_client.client.setex(
                key,
                self.PROCESS_TTL,
                redis_client._serialize(process_data)
            )

            logger.debug(f"  Process {process_id} updated in Redis with URLs: download={process_data.get('download_url')}, labels={process_data.get('labels_only_url')}, report={process_data.get('report_url')}")
            return True

        except Exception as e:
            logger.error(f"Failed to update process {process_id}: {e}")
            return False

    async def get_process(self, process_id: int) -> Optional[Dict[str, Any]]:
        """Get process status from Redis"""
        try:
            key = f"{self.PROCESS_PREFIX}{process_id}"
            data = await redis_client.client.get(key)
            if data:
                return redis_client._deserialize(data)
            return None
        except Exception as e:
            logger.error(f"Failed to get process {process_id}: {e}")
            return None

    async def increment_counter(self, process_id: int, field: str, amount: int = 1) -> Optional[int]:
        """Atomically increment a counter in process data"""
        try:
            key = f"{self.PROCESS_PREFIX}{process_id}"

            # Lua script for atomic increment
            lua_script = """
            local data = redis.call('GET', KEYS[1])
            if data then
                local process = cjson.decode(data)
                process[ARGV[1]] = (process[ARGV[1]] or 0) + tonumber(ARGV[2])
                process['updated_at'] = ARGV[3]
                redis.call('SETEX', KEYS[1], ARGV[4], cjson.encode(process))
                return process[ARGV[1]]
            end
            return nil
            """

            result = await redis_client.client.eval(
                lua_script,
                1,
                key,
                field,
                str(amount),
                datetime.utcnow().isoformat(),
                str(self.PROCESS_TTL)
            )

            return int(result) if result else None

        except Exception as e:
            logger.error(f"Failed to increment counter for process {process_id}: {e}")
            return None

    async def get_user_recent_processes(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent processes for a user"""
        try:
            user_key = f"{self.USER_PROCESSES_PREFIX}{user_id}"

            # Get recent process IDs (last 10)
            process_ids = await redis_client.client.zrevrange(user_key, 0, limit - 1)

            processes = []
            for pid_bytes in process_ids:
                pid = int(pid_bytes.decode() if isinstance(pid_bytes, bytes) else pid_bytes)
                process = await self.get_process(pid)
                if process:
                    processes.append(process)

            return processes

        except Exception as e:
            logger.error(f"Failed to get user processes: {e}")
            return []

    async def delete_process(self, process_id: int):
        """Delete process data (cleanup)"""
        try:
            key = f"{self.PROCESS_PREFIX}{process_id}"

            # Get process to get user_id
            data = await redis_client.client.get(key)
            if data:
                process = redis_client._deserialize(data)
                user_id = process.get("user_id")

                # Remove from user's process list
                if user_id:
                    user_key = f"{self.USER_PROCESSES_PREFIX}{user_id}"
                    await redis_client.client.zrem(user_key, str(process_id))

            # Delete process data
            await redis_client.client.delete(key)
            logger.debug(f"  Process {process_id} deleted from Redis")

        except Exception as e:
            logger.error(f"Failed to delete process {process_id}: {e}")

    async def cleanup_old_processes(self, hours: int = 24):
        """Clean up processes older than specified hours"""
        try:
            cutoff = datetime.utcnow().timestamp() - (hours * 3600)

            # Scan all process keys
            pattern = f"{self.PROCESS_PREFIX}*"
            async for key in redis_client.client.scan_iter(match=pattern):
                data = await redis_client.client.get(key)
                if data:
                    process = redis_client._deserialize(data)
                    created_at = datetime.fromisoformat(process.get("created_at", "2000-01-01"))
                    if created_at.timestamp() < cutoff:
                        await self.delete_process(int(process["process_id"]))

            logger.info(f"  Cleaned up processes older than {hours} hours")

        except Exception as e:
            logger.error(f"Failed to cleanup old processes: {e}")

# Global instance
redis_process = RedisProcessTracker()
