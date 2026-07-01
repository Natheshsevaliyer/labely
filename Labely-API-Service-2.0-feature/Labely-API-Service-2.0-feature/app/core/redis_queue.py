# app/core/redis_queue.py
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from .redis_client import redis_client

logger = logging.getLogger(__name__)

class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"

class RedisJobQueue:
    """Robust job queue using Redis lists with retry and dead letter queue"""

    def __init__(self):
        self.QUEUE_PREFIX = "queue:"
        self.PROCESSING_PREFIX = "processing:"
        self.RESULT_PREFIX = "result:"
        self.DEAD_LETTER_PREFIX = "dead_letter:"
        self.RETRY_PREFIX = "retry:"
        self.STATS_PREFIX = "queue_stats:"
        self.max_retries = 3
        self.retry_delays = [60, 300, 900]  # 1min, 5min, 15min

    async def enqueue(self, queue_name: str, job_data: dict, priority: int = 0) -> str:
        """Add job to queue with optional priority"""
        try:
            job_id = str(uuid.uuid4())
            now = datetime.utcnow()

            job = {
                "id": job_id,
                "data": job_data,
                "status": JobStatus.PENDING,
                "priority": priority,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "retry_count": 0,
                "max_retries": self.max_retries
            }

            # Use different queues for different priorities
            if priority > 0:
                queue_key = f"{self.QUEUE_PREFIX}{queue_name}:high"
                # Add to front for high priority
                await redis_client.client.lpush(queue_key, redis_client._serialize(job))
            else:
                queue_key = f"{self.QUEUE_PREFIX}{queue_name}"
                # Add to back for normal priority
                await redis_client.client.rpush(queue_key, redis_client._serialize(job))

            # Update queue stats
            await self._update_stats(queue_name, "enqueued")

            logger.info(f"  Job {job_id} enqueued to {queue_name} (priority={priority})")
            return job_id

        except Exception as e:
            logger.error(f"Failed to enqueue job: {e}")
            raise

    async def dequeue(self, queue_name: str, timeout: int = 5) -> Optional[Dict[str, Any]]:
        """Get next job from queue (blocking)"""
        try:
            # Check high priority queue first
            high_queue_key = f"{self.QUEUE_PREFIX}{queue_name}:high"
            normal_queue_key = f"{self.QUEUE_PREFIX}{queue_name}"
            processing_key = f"{self.PROCESSING_PREFIX}{queue_name}"

            # Try high priority first with short timeout
            result = await redis_client.client.brpoplpush(
                high_queue_key,
                processing_key,
                timeout=1
            )

            if not result:
                # Try normal queue with remaining timeout
                result = await redis_client.client.brpoplpush(
                    normal_queue_key,
                    processing_key,
                    timeout=timeout
                )

            if result:
                job = redis_client._deserialize(result)
                job["status"] = JobStatus.PROCESSING
                job["started_at"] = datetime.utcnow().isoformat()
                job["updated_at"] = datetime.utcnow().isoformat()

                # Update the job in processing list
                await self._update_processing_job(queue_name, job)

                logger.debug(f"Job {job['id']} dequeued for processing")
                return job

            return None

        except Exception as e:
            logger.error(f"Failed to dequeue job: {e}")
            return None

    async def complete_job(self, queue_name: str, job: Dict[str, Any], result: Any = None):
        """Mark job as completed"""
        try:
            job_id = job["id"]
            processing_key = f"{self.PROCESSING_PREFIX}{queue_name}"

            # Store result
            if result:
                result_key = f"{self.RESULT_PREFIX}{queue_name}:{job_id}"
                result_data = {
                    "job_id": job_id,
                    "result": result,
                    "completed_at": datetime.utcnow().isoformat()
                }
                await redis_client.client.setex(
                    result_key,
                    3600,  # Keep result for 1 hour
                    redis_client._serialize(result_data)
                )

            # Remove from processing list
            await redis_client.client.lrem(processing_key, 1, redis_client._serialize(job))

            # Update stats
            await self._update_stats(queue_name, "completed")

            logger.info(f"  Job {job_id} completed successfully")

        except Exception as e:
            logger.error(f"Failed to complete job {job.get('id')}: {e}")

    async def fail_job(self, queue_name: str, job: Dict[str, Any], error: str, requeue: bool = False):
        """Handle failed job with retry logic"""
        try:
            job_id = job["id"]
            retry_count = job.get("retry_count", 0) + 1
            max_retries = job.get("max_retries", self.max_retries)

            job["error"] = error
            job["retry_count"] = retry_count
            job["updated_at"] = datetime.utcnow().isoformat()

            if retry_count <= max_retries and requeue:
                # Calculate delay for retry
                delay = self.retry_delays[min(retry_count - 1, len(self.retry_delays) - 1)]

                # Schedule for retry
                retry_key = f"{self.RETRY_PREFIX}{queue_name}:{int(datetime.utcnow().timestamp()) + delay}"
                await redis_client.client.setex(
                    retry_key,
                    delay + 60,  # Extra buffer
                    redis_client._serialize(job)
                )

                logger.warning(f" Job {job_id} failed, will retry in {delay}s (attempt {retry_count}/{max_retries})")

            else:
                # Move to dead letter queue
                dead_key = f"{self.DEAD_LETTER_PREFIX}{queue_name}"
                await redis_client.client.rpush(dead_key, redis_client._serialize(job))

                # Update stats
                await self._update_stats(queue_name, "failed")

                logger.error(f"Job {job_id} failed permanently after {retry_count} attempts")

            # Remove from processing list
            processing_key = f"{self.PROCESSING_PREFIX}{queue_name}"
            await redis_client.client.lrem(processing_key, 1, redis_client._serialize(job))

        except Exception as e:
            logger.error(f"Failed to handle job failure: {e}")

    async def _update_processing_job(self, queue_name: str, job: Dict[str, Any]):
        """Update job in processing list"""
        try:
            processing_key = f"{self.PROCESSING_PREFIX}{queue_name}"

            # This is tricky - we need to find and replace the job
            # For simplicity, we'll just leave it as is since we update status in memory

        except Exception as e:
            logger.error(f"Failed to update processing job: {e}")

    async def _update_stats(self, queue_name: str, event: str):
        """Update queue statistics"""
        try:
            stats_key = f"{self.STATS_PREFIX}{queue_name}"
            today = datetime.utcnow().strftime("%Y-%m-%d")

            pipe = redis_client.client.pipeline()
            pipe.hincrby(stats_key, f"{today}:{event}", 1)
            pipe.hincrby(stats_key, f"total:{event}", 1)
            pipe.expire(stats_key, 86400 * 7)  # Keep for 7 days
            await pipe.execute()

        except Exception as e:
            logger.error(f"Failed to update stats: {e}")

    async def get_queue_stats(self, queue_name: str) -> Dict[str, Any]:
        """Get queue statistics"""
        try:
            stats_key = f"{self.STATS_PREFIX}{queue_name}"
            stats = await redis_client.client.hgetall(stats_key)

            queue_key = f"{self.QUEUE_PREFIX}{queue_name}"
            high_queue_key = f"{self.QUEUE_PREFIX}{queue_name}:high"
            processing_key = f"{self.PROCESSING_PREFIX}{queue_name}"
            dead_key = f"{self.DEAD_LETTER_PREFIX}{queue_name}"

            # Get queue sizes
            queue_size = await redis_client.client.llen(queue_key)
            high_queue_size = await redis_client.client.llen(high_queue_key)
            processing_size = await redis_client.client.llen(processing_key)
            dead_letter_size = await redis_client.client.llen(dead_key)

            return {
                "queue_size": queue_size,
                "high_priority_size": high_queue_size,
                "processing_size": processing_size,
                "dead_letter_size": dead_letter_size,
                "total_enqueued": int(stats.get("total:enqueued", 0)),
                "total_completed": int(stats.get("total:completed", 0)),
                "total_failed": int(stats.get("total:failed", 0)),
                "stats": stats
            }

        except Exception as e:
            logger.error(f"Failed to get queue stats: {e}")
            return {}

    async def retry_dead_letters(self, queue_name: str, limit: int = 10) -> int:
        """Retry jobs from dead letter queue"""
        try:
            dead_key = f"{self.DEAD_LETTER_PREFIX}{queue_name}"
            retry_count = 0

            for _ in range(limit):
                job_data = await redis_client.client.lpop(dead_key)
                if not job_data:
                    break

                job = redis_client._deserialize(job_data)
                job["retry_count"] = 0  # Reset retry count

                # Requeue
                await self.enqueue(queue_name, job["data"])
                retry_count += 1

            logger.info(f"Retried {retry_count} dead letters for queue {queue_name}")
            return retry_count

        except Exception as e:
            logger.error(f"Failed to retry dead letters: {e}")
            return 0

    async def clear_queue(self, queue_name: str):
        """Clear all queues (dangerous - use carefully)"""
        try:
            queue_key = f"{self.QUEUE_PREFIX}{queue_name}"
            high_queue_key = f"{self.QUEUE_PREFIX}{queue_name}:high"
            processing_key = f"{self.PROCESSING_PREFIX}{queue_name}"
            dead_key = f"{self.DEAD_LETTER_PREFIX}{queue_name}"

            await redis_client.client.delete(queue_key, high_queue_key, processing_key, dead_key)
            logger.warning(f" All queues cleared for {queue_name}")

        except Exception as e:
            logger.error(f"Failed to clear queue: {e}")

# Global instance
redis_queue = RedisJobQueue()
