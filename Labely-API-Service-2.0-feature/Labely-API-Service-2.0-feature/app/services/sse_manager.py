# app/services/sse_manager.py
import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Set

from alembic.environment import List

logger = logging.getLogger(__name__)

class SSEManager:
    """Simple SSE manager without external dependencies."""

    def __init__(self):
        self.connections: Dict[str, Set[asyncio.Queue]] = {}
        self.process_status: Dict[str, Dict[str, Any]] = {}  # Store final status with URLs

    async def connect(self, process_id: str) -> asyncio.Queue:
        """Create a new connection queue."""
        queue = asyncio.Queue()

        if process_id not in self.connections:
            self.connections[process_id] = set()

        self.connections[process_id].add(queue)
        return queue

    def disconnect(self, process_id: str, queue: asyncio.Queue):
        """Remove a connection."""
        if process_id in self.connections:
            self.connections[process_id].discard(queue)
            if not self.connections[process_id]:
                del self.connections[process_id]
                # Clean up status when no connections left
                self.process_status.pop(process_id, None)

    def mark_completed(self, process_id: str, status_data: Dict[str, Any]):
        """Mark process as completed with full status data including URLs."""
        self.process_status[process_id] = status_data

    def is_completed(self, process_id: str) -> bool:
        """Check if process is completed."""
        return process_id in self.process_status

    def get_completed_status(self, process_id: str) -> Optional[Dict[str, Any]]:
        """Get completed status data for a process."""
        return self.process_status.get(process_id)

    async def broadcast(self, process_id: str, data: Dict[str, Any]):
        """Send update to all clients."""
        if process_id not in self.connections:
            return

        message = f"event: status_update\ndata: {json.dumps(data, default=str)}\n\n"

        disconnected = set()
        for queue in self.connections[process_id]:
            try:
                await queue.put(message)
            except Exception:
                disconnected.add(queue)

        for queue in disconnected:
            self.disconnect(process_id, queue)

    async def broadcast_progress(self, process_id: str, processed: int, total: int,
                                successful: int, failed: int, status: str,
                                download_url: Optional[str] = None,
                                labels_only_url: Optional[str] = None,
                                report_url: Optional[str] = None,
                                failed_orders: Optional[List[Dict]] = None):  # ← ADD THIS PARAMETER
        """Broadcast progress update with optional URLs and failed orders."""
        data = {
            "process_id": int(process_id),
            "status": status,
            "processed": processed,
            "total": total,
            "successful": successful,
            "failed": failed,
            "progress": round((processed / total * 100) if total > 0 else 0, 2),
            "timestamp": datetime.utcnow().isoformat()
        }

        # Add URLs if provided
        if download_url:
            data["download_url"] = download_url
            logger.debug(f"Adding download_url to broadcast: {download_url}")
        if labels_only_url:
            data["labels_only_url"] = labels_only_url
            logger.debug(f"Adding labels_only_url to broadcast: {labels_only_url}")
        if report_url:
            data["report_url"] = report_url
            logger.debug(f"Adding report_url to broadcast: {report_url}")

        # ← ADD THIS BLOCK
        if failed_orders:
            data["failed_orders"] = failed_orders
            data["failed_count"] = len(failed_orders)
            logger.debug(f"Adding {len(failed_orders)} failed orders to broadcast")

        await self.broadcast(process_id, data)

        # If final status, mark as completed with full data
        if status in ['Completed', 'Failed', 'Partial']:
            self.mark_completed(process_id, data)

# Global instance
sse_manager = SSEManager()
