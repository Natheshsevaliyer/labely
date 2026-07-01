"""Tracking-number update service – bulk updates to Mirakl with batch tracking."""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ValidationException
from app.models import (
    BatchStatusEnum,
    TrackingBatch,
    TrackingStatusEnum,
    TrackingUpdate,
)
from app.services.base import BaseService
from app.services.dashboard_service import DashboardService
from app.services.helpers.pagination import build_page_response, paginate_query
from app.services.mirakl.tracking_service import mirakl_tracking_service
from app.services.sse_manager import sse_manager

logger = logging.getLogger(__name__)


class TrackingService(BaseService[TrackingUpdate]):
    """Manages sending generated tracking numbers to Mirakl."""

    def __init__(self, db: Session) -> None:
        super().__init__(TrackingUpdate, db)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def _ready_for_update_query(self, user_id: int, carrier_filter: Optional[str]):
        """Base query for orders eligible for tracking update."""
        query = self.db.query(TrackingUpdate).filter(
            TrackingUpdate.user_id == user_id,
            TrackingUpdate.label_generated == True,
            TrackingUpdate.tracking_number.isnot(None),
            TrackingUpdate.tracking_updated == False,

        )
        if carrier_filter:
            query = query.filter(TrackingUpdate.carrier_used == carrier_filter)
        return query

    # ------------------------------------------------------------------
    # Public – listing
    # ------------------------------------------------------------------

    async def get_ready_orders(
        self,
        user_id: int,
        carrier_filter: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Return paginated orders ready for tracking update (no date filter)."""
        query = self._ready_for_update_query(user_id, carrier_filter).options(
            joinedload(TrackingUpdate.user),
            joinedload(TrackingUpdate.process),
            joinedload(TrackingUpdate.batch),
        ).order_by(TrackingUpdate.order_date.desc())

        total, records = paginate_query(query, page, limit)
        items = [self._format_record(r) for r in records]

        status_counts: Dict[str, int] = {}
        for item in items:
            s = item["tracking_status"]
            status_counts[s] = status_counts.get(s, 0) + 1

        logger.info("Ready-for-tracking user=%d: %d total, %d on page", user_id, total, len(items))

        return build_page_response(
            items, total, page, limit,
            extra={
                "summary": {
                    "total_eligible": sum(1 for i in items if i["can_update"]),
                    "status_breakdown": status_counts,
                    "filters_applied": {"carrier_filter": carrier_filter},
                }
            },
        )

    # ------------------------------------------------------------------
    # Public – bulk update
    # ------------------------------------------------------------------

    async def bulk_update(
        self,
        user_id: int,
        order_ids: List[str],
        force_update: bool = False,
        carrier_filter: Optional[str] = None,
        # Kept for backward compatibility – not used
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Bulk-update tracking numbers for the specified orders in Mirakl."""
        if not order_ids:
            raise ValidationException("No order IDs provided")

        records = self.db.query(TrackingUpdate).filter(
            TrackingUpdate.order_id.in_(order_ids),
            TrackingUpdate.user_id == user_id,
        ).all()

        records_map = {r.order_id: r for r in records}

        # Create a batch record
        batch_id = str(uuid.uuid4())
        batch = TrackingBatch(
            batch_id=batch_id, user_id=user_id,
            total_orders=len(order_ids), status=BatchStatusEnum.PROCESSING,
        )
        self.db.add(batch)
        self.db.commit()

        logger.info("Tracking batch %s created: %d orders", batch_id, len(order_ids))

        asyncio.create_task(
            self._process_batch(batch_id, order_ids, records_map, user_id, force_update)
        )

        return {
            "success": True,
            "message": f"Tracking update started for {len(order_ids)} orders",
            "batch_id": batch_id,
            "total_orders": len(order_ids),
        }

    # ------------------------------------------------------------------
    # Background task
    # ------------------------------------------------------------------

    async def _process_batch(
        self,
        batch_id: str,
        order_ids: List[str],
        records_map: Dict[str, TrackingUpdate],  # This is detached
        user_id: int,
        force_update: bool,
    ) -> None:
        """Background: send tracking numbers to Mirakl one-by-one, streaming
        SSE progress after each order completes."""
        from app.core.database import SessionLocal

        db = SessionLocal()
        total = len(order_ids)
        success_count = failed_count = processed_count = 0

        logger.info("Tracking batch %s: starting for %d orders", batch_id, len(order_ids))

        # Broadcast initial event so the frontend knows the batch is live
        await sse_manager.broadcast(batch_id, {
            "event": "tracking_start",
            "batch_id": batch_id,
            "total": total,
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "status": "processing",
        })

        try:
            for oid in order_ids:
                # RELOAD the record in the current session instead of using detached one
                record = db.query(TrackingUpdate).filter(
                    TrackingUpdate.order_id == oid,
                    TrackingUpdate.user_id == user_id
                ).first()

                # Remove or comment out the old records_map usage
                # record = records_map.get(oid)  # DON'T USE THIS - it's detached

                if not record:
                    logger.warning("Tracking batch %s: no record for order %s – skipping", batch_id, oid)
                    failed_count += 1
                    processed_count += 1
                    await sse_manager.broadcast(batch_id, {
                        "event": "tracking_update",
                        "batch_id": batch_id,
                        "order_id": oid,
                        "success": False,
                        "error": "No tracking record found",
                        "processed": processed_count,
                        "total": total,
                        "successful": success_count,
                        "failed": failed_count,
                        "progress": round(processed_count / total * 100, 2),
                    })
                    continue

                # Now this will work because record is attached to db session
                if record.tracking_updated and not force_update:
                    logger.debug("Tracking batch %s: order %s already updated – skipping", batch_id, oid)
                    processed_count += 1
                    await sse_manager.broadcast(batch_id, {
                        "event": "tracking_update",
                        "batch_id": batch_id,
                        "order_id": oid,
                        "success": True,
                        "skipped": True,
                        "reason": "Already updated",
                        "processed": processed_count,
                        "total": total,
                        "successful": success_count,
                        "failed": failed_count,
                        "progress": round(processed_count / total * 100, 2),
                    })
                    continue

                try:
                    result = mirakl_tracking_service.update_order_tracking_with_carrier(
                        oid, record.tracking_number, record.carrier_used
                    )

                    # Reload from DB (this session might differ)
                    db_record = db.query(TrackingUpdate).filter(TrackingUpdate.order_id == oid).first()
                    if db_record:
                        if result.get("success"):
                            db_record.tracking_updated = True
                            db_record.status = TrackingStatusEnum.GENERATED
                            db_record.batch_id = batch_id
                            db_record.error_message = None
                            db_record.update_attempts = (db_record.update_attempts or 0) + 1
                            db_record.last_attempt = datetime.utcnow()
                            db.commit()
                            success_count += 1
                            logger.info("Tracking batch %s: updated order %s", batch_id, oid)
                        else:
                            db_record.error_message = result.get("error", "Unknown error")
                            db_record.update_attempts = (db_record.update_attempts or 0) + 1
                            db_record.last_attempt = datetime.utcnow()
                            db.commit()
                            failed_count += 1
                            logger.error(
                                "Tracking batch %s: failed for order %s – %s",
                                batch_id, oid, db_record.error_message,
                            )

                    processed_count += 1
                    await sse_manager.broadcast(batch_id, {
                        "event": "tracking_update",
                        "batch_id": batch_id,
                        "order_id": oid,
                        "success": result.get("success", False),
                        "error": result.get("error") if not result.get("success") else None,
                        "tracking_number": record.tracking_number,
                        "processed": processed_count,
                        "total": total,
                        "successful": success_count,
                        "failed": failed_count,
                        "progress": round(processed_count / total * 100, 2),
                    })

                except Exception as exc:
                    logger.error(
                        "Tracking batch %s: exception for order %s – %s",
                        batch_id, oid, exc, exc_info=True,
                    )
                    failed_count += 1
                    processed_count += 1
                    await sse_manager.broadcast(batch_id, {
                        "event": "tracking_update",
                        "batch_id": batch_id,
                        "order_id": oid,
                        "success": False,
                        "error": str(exc),
                        "processed": processed_count,
                        "total": total,
                        "successful": success_count,
                        "failed": failed_count,
                        "progress": round(processed_count / total * 100, 2),
                    })

                await asyncio.sleep(0.1)

            # Finalise batch record
            batch = db.query(TrackingBatch).filter(TrackingBatch.batch_id == batch_id).first()
            if batch:
                batch.successful = success_count
                batch.failed = failed_count
                batch.processed_orders = processed_count
                batch.status = BatchStatusEnum.COMPLETED
                batch.completed_at = datetime.utcnow()
                db.commit()

            logger.info("Tracking batch %s done: ok=%d fail=%d", batch_id, success_count, failed_count)

            # Add cache invalidation:
            db.close()  # Don't add before this
            # But you need a new db session, so add before db.close():

            # Get a new db session for dashboard service
            from app.core.database import SessionLocal
            dashboard_db = SessionLocal()
            dashboard_service = DashboardService(dashboard_db)
            await dashboard_service.invalidate_cache(user_id)
            dashboard_db.close()

            # Broadcast completion
            await sse_manager.broadcast(batch_id, {
                "event": "tracking_complete",
                "batch_id": batch_id,
                "status": "completed",
                "total": total,
                "processed": processed_count,
                "successful": success_count,
                "failed": failed_count,
                "progress": 100.0,
            })

        finally:
            db.close()

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _format_record(self, record: TrackingUpdate) -> Dict[str, Any]:
        can_update = (
            record.label_generated
            and record.tracking_number
            and not record.tracking_updated
            and record.status == TrackingStatusEnum.GENERATED
        )
        return {
            "order_id": record.order_id,
            "order_date": record.order_date.isoformat() if record.order_date else "",
            "tracking_number": record.tracking_number,
            "process_id": record.process_id,
            "batch_id": record.batch_id,
            "campaign_number": record.campaign_number or "",
            "order_state": record.order_state or "",
            "carrier": record.carrier_used or "",
            "country": record.country or "",
            "commercial_id": record.commercial_id or "",
            "label_generated_count": record.label_generated_count,
            "label_status": record.status.value if record.status else "UNKNOWN",
            "tracking_status": "READY_FOR_UPDATE" if can_update else "NOT_READY",
            "status_reason": self._status_reason(record),
            "can_update": can_update,
            "update_attempts": record.update_attempts,
            "last_attempt": record.last_attempt.isoformat() if record.last_attempt else None,
        }

    @staticmethod
    def _status_reason(record: TrackingUpdate) -> str:
        if not record.label_generated:
            return "Label not generated yet"
        if not record.tracking_number:
            return "No tracking number available"
        if record.tracking_updated:
            return "Already updated in Mirakl"
        if record.error_message:
            return f"Previous error: {record.error_message[:50]}"
        if record.status != TrackingStatusEnum.GENERATED:
            return f"Status: {record.status.value if record.status else 'Unknown'}"
        return "Ready for tracking update"
