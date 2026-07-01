"""Shipment confirmation service – validate, confirm, and archive shipments."""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ValidationException
from app.models import Shipment, ShipmentBatch, ShipmentStatusEnum, TrackingUpdate
from app.services.base import BaseService
from app.services.dashboard_service import DashboardService
from app.services.helpers.pagination import build_page_response, paginate_query
from app.services.mirakl.shipment_service import mirakl_shipment_service
from app.services.sse_manager import sse_manager

logger = logging.getLogger(__name__)


def _shipment_item(record: TrackingUpdate, tracking_url: Optional[str], validation: Dict) -> Dict:
    """Serialise a TrackingUpdate record for shipment-related API responses."""
    return {
        "id": record.id,
        "order_id": record.order_id,
        "commercial_id": record.commercial_id,
        "tracking_number": record.tracking_number,
        "carrier": record.carrier_used,
        "tracking_url": tracking_url,
        "process_id": record.process_id,
        "order_state": record.order_state,
        "order_date": record.order_date.isoformat() if record.order_date else None,
        "campaign_number": record.campaign_number,
        "ean_code": record.ean_code,
        "label_generated_count": record.label_generated_count,
        "shipment_confirmed": record.shipment_confirmed,
        "validation_passed": validation["valid"],
        "validation_checks": validation["checks"],
        "warnings": validation["warnings"],
    }


def _validate_record(record: TrackingUpdate) -> Dict:
    """Run Mirakl validation for a single tracking record."""
    return mirakl_shipment_service.validate_tracking_for_shipment(
        record.order_id, record.tracking_number, ""  # tracking URL deprecated
    )


def _build_carrier_summary(items: List[Dict]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for item in items:
        c = item.get("carrier") or "Unknown"
        summary[c] = summary.get(c, 0) + 1
    return summary


class ShipmentService(BaseService[Shipment]):
    """Orchestrates shipment confirmation against the Mirakl OR24 API."""

    def __init__(self, db: Session) -> None:
        super().__init__(Shipment, db)

    # ------------------------------------------------------------------
    # Ready shipments (paginated)
    # ------------------------------------------------------------------

    async def get_ready_shipments(
        self,
        user_id: int,
        carrier_filter: Optional[str] = None,
        include_confirmed: bool = False,
        page: int = 1,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Return all orders ready for shipment confirmation (no date filter)."""
        query = self._ready_query(user_id, carrier_filter, include_confirmed)
        total, records = paginate_query(
            query.options(
                joinedload(TrackingUpdate.user),
                joinedload(TrackingUpdate.process),
            ).order_by(TrackingUpdate.order_date.desc()),
            page,
            limit,
        )

        items = [_shipment_item(r, None, _validate_record(r)) for r in records]
        by_carrier = _build_carrier_summary(items)
        valid_count = sum(1 for i in items if i["validation_passed"])

        logger.info("Ready shipments for user=%d: %d total, %d on this page", user_id, total, len(items))

        return build_page_response(
            items, total, page, limit,
            extra={
                "summary": {
                    "by_carrier": by_carrier,
                    "validation_passed": valid_count,
                    "ready_to_ship": sum(1 for i in items if i["validation_passed"] and not i["shipment_confirmed"]),
                    "filters_applied": {"carrier_filter": carrier_filter, "include_confirmed": include_confirmed},
                }
            },
        )

    async def get_ready_by_date(
        self,
        user_id: int,
        start_date: str,
        end_date: str,
        carrier_filter: Optional[str] = None,
        include_confirmed: bool = False,
    ) -> Dict[str, Any]:
        """Return orders ready for confirmation within an order-date range."""
        start, end = self._parse_date_range(start_date, end_date)
        query = self._ready_query(user_id, carrier_filter, include_confirmed).filter(
            TrackingUpdate.order_date >= start,
            TrackingUpdate.order_date <= end,
        )
        records = query.all()
        items = [_shipment_item(r, None, _validate_record(r)) for r in records]
        by_carrier = _build_carrier_summary(items)

        logger.info(
            "Ready-by-date for user=%d [%s → %s]: %d records",
            user_id, start_date, end_date, len(items),
        )

        return {
            "total": len(items),
            "date_range": {"start_date": start_date, "end_date": end_date},
            "carrier_filter": carrier_filter,
            "include_confirmed": include_confirmed,
            "shipments": items,
            "summary": {
                "by_carrier": by_carrier,
                "validation_passed": sum(1 for i in items if i["validation_passed"]),
                "ready_to_ship": sum(1 for i in items if i["validation_passed"] and not i["shipment_confirmed"]),
            },
        }

    # ------------------------------------------------------------------
    # Shipment confirmation
    # ------------------------------------------------------------------

    async def confirm_shipments(
        self,
        user_id: int,
        order_ids: List[str],
        validate_only: bool = False,
        force_confirm: bool = False,
    ) -> Dict[str, Any]:
        """Confirm shipment for a list of order IDs (optionally validation-only)."""
        if not order_ids:
            raise ValidationException("No order IDs provided")

        batch_id = str(uuid.uuid4())
        validation = await self._validate_orders(user_id, order_ids, force_confirm)

        if validate_only:
            logger.info("Validate-only mode for batch %s (%d orders)", batch_id, len(order_ids))
            return {
                "total_processed": len(order_ids), "successful": 0, "failed": 0,
                "batch_id": batch_id,
                "results": [
                    {"order_id": r["order_id"], "success": False,
                     "message": "Validation only", "error": ", ".join(r.get("warnings", []))}
                    for r in validation["results"]
                ],
            }

        orders_to_ship = [r for r in validation["results"] if r["can_ship"] or force_confirm]
        skipped = [
            {"order_id": r["order_id"], "reason": ", ".join(r.get("warnings", []))}
            for r in validation["results"] if not (r["can_ship"] or force_confirm)
        ]

        if not orders_to_ship:
            raise ValidationException("No orders ready for confirmation. Use force_confirm=true to override.")

        batch = ShipmentBatch(
            batch_id=batch_id, user_id=user_id,
            total_orders=len(orders_to_ship), status=ShipmentStatusEnum.PROCESSING,
        )
        self.db.add(batch)
        self.db.commit()
        logger.info("Shipment batch %s created: %d orders", batch_id, len(orders_to_ship))

        asyncio.create_task(self._confirm_shipments_batch(batch_id, orders_to_ship, user_id))

        return {
            "total_processed": len(order_ids), "successful": 0, "failed": 0,
            "batch_id": batch_id,
            "results": [
                {"order_id": o["order_id"], "success": False, "message": "Confirmation started"}
                for o in orders_to_ship
            ],
        }

    async def confirm_by_date(
        self,
        user_id: int,
        start_date: str,
        end_date: str,
        carrier_filter: Optional[str] = None,
        force_confirm: bool = False,
        max_orders: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Confirm all eligible shipments within a date range."""
        ready = await self.get_ready_by_date(user_id, start_date, end_date, carrier_filter)

        order_ids, skipped = [], []
        for s in ready["shipments"]:
            if s["validation_passed"] or force_confirm:
                if not s["shipment_confirmed"]:
                    order_ids.append(s["order_id"])
                else:
                    skipped.append({"order_id": s["order_id"], "reason": "Already confirmed"})
            else:
                skipped.append({"order_id": s["order_id"], "reason": "Validation failed", "warnings": s["warnings"]})

        if max_orders:
            order_ids = order_ids[:max_orders]

        if not order_ids:
            raise ValidationException("No eligible orders found in the specified date range")

        batch_id = str(uuid.uuid4())
        start, end = self._parse_date_range(start_date, end_date)
        batch = ShipmentBatch(
            batch_id=batch_id, user_id=user_id,
            total_orders=len(order_ids), status=ShipmentStatusEnum.PROCESSING,
            start_date=start, end_date=end,
        )
        self.db.add(batch)
        self.db.commit()

        asyncio.create_task(
            self._confirm_shipments_batch(batch_id, [{"order_id": oid} for oid in order_ids], user_id)
        )

        logger.info("Date-range confirmation batch %s: %d orders [%s → %s]", batch_id, len(order_ids), start_date, end_date)

        return {
            "success": True,
            "message": f"Confirmation started for {len(order_ids)} orders",
            "batch_id": batch_id,
            "total_eligible": len(ready["shipments"]),
            "processing": len(order_ids),
            "skipped": len(skipped),
            "skipped_details": skipped[:10],
            "date_range": {"start_date": start_date, "end_date": end_date},
            "carrier_filter": carrier_filter,
        }

    # ------------------------------------------------------------------
    # Batch status / history
    # ------------------------------------------------------------------

    def get_batch_status(self, batch_id: str, user_id: int) -> Optional[Dict[str, Any]]:
        batch = self.db.query(ShipmentBatch).filter(
            ShipmentBatch.batch_id == batch_id,
            ShipmentBatch.user_id == user_id,
        ).first()
        if not batch:
            return None

        shipments = self.db.query(Shipment).filter(
            Shipment.batch_id == batch_id, Shipment.user_id == user_id
        ).all()

        progress = round((batch.processed_orders / batch.total_orders * 100) if batch.total_orders else 0, 2)

        return {
            "batch_id": batch.batch_id,
            "status": batch.status.value,
            "total_orders": batch.total_orders,
            "processed_orders": batch.processed_orders,
            "successful": batch.successful,
            "failed": batch.failed,
            "progress": progress,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
            "shipments": [
                {"order_id": s.order_id, "status": s.shipment_status.value,
                 "success": s.shipment_confirmed, "error": s.error_message}
                for s in shipments
            ],
        }

    def get_batches(self, user_id: int, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        query = self.db.query(ShipmentBatch).filter(
            ShipmentBatch.user_id == user_id
        ).order_by(ShipmentBatch.created_at.desc())

        total, batches = paginate_query(query, page, limit)
        items = [
            {
                "batch_id": b.batch_id,
                "status": b.status.value,
                "total_orders": b.total_orders,
                "successful": b.successful,
                "failed": b.failed,
                "progress": round((b.processed_orders / b.total_orders * 100) if b.total_orders else 0, 2),
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "completed_at": b.completed_at.isoformat() if b.completed_at else None,
            }
            for b in batches
        ]
        return build_page_response(items, total, page, limit)

    def get_history(
        self,
        user_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        carrier_filter: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> Dict[str, Any]:
        query = self.db.query(Shipment).filter(Shipment.user_id == user_id)

        if start_date and end_date:
            try:
                s, e = self._parse_date_range(start_date, end_date)
                query = query.filter(Shipment.shipment_date >= s, Shipment.shipment_date <= e)
            except ValidationException:
                logger.warning("Invalid date range %s – %s; ignoring filter", start_date, end_date)
        if carrier_filter:
            query = query.filter(Shipment.carrier_used == carrier_filter)

        total, shipments = paginate_query(query.order_by(Shipment.shipment_date.desc()), page, limit)

        items = [
            {
                "id": s.id, "order_id": s.order_id, "commercial_id": s.commercial_id,
                "tracking_number": s.tracking_number, "carrier": s.carrier_used,
                "tracking_url": s.tracking_url, "order_state": s.order_state,
                "campaign_number": s.campaign_number, "ean_code": s.ean_code,
                "shipment_confirmed": s.shipment_confirmed,
                "shipment_date": s.shipment_date.isoformat() if s.shipment_date else None,
                "status": s.shipment_status.value, "error": s.error_message,
            }
            for s in shipments
        ]
        return build_page_response(
            items, total, page, limit,
            extra={"summary": {"filters_applied": {"start_date": start_date, "end_date": end_date, "carrier_filter": carrier_filter}}},
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ready_query(self, user_id: int, carrier_filter: Optional[str], include_confirmed: bool):
        query = self.db.query(TrackingUpdate).filter(
            TrackingUpdate.user_id == user_id,
            TrackingUpdate.label_generated == True,
            TrackingUpdate.tracking_updated == True,
            TrackingUpdate.tracking_number.isnot(None),
        )
        if carrier_filter:
            query = query.filter(TrackingUpdate.carrier_used == carrier_filter)
        if not include_confirmed:
            query = query.filter(TrackingUpdate.shipment_confirmed == False)
        return query

    async def _validate_orders(
        self, user_id: int, order_ids: List[str], force_confirm: bool = False
    ) -> Dict[str, Any]:
        records = {
            r.order_id: r
            for r in self.db.query(TrackingUpdate).filter(
                TrackingUpdate.order_id.in_(order_ids),
                TrackingUpdate.user_id == user_id,
                TrackingUpdate.label_generated == True,
                TrackingUpdate.tracking_number.isnot(None),
            ).all()
        }

        results, valid_count = [], 0
        for oid in order_ids:
            record = records.get(oid)
            if not record:
                results.append({
                    "order_id": oid, "tracking_number": None, "tracking_url": None,
                    "carrier": None, "validation_passed": False, "validation_checks": {},
                    "warnings": ["No tracking record found"], "can_ship": False,
                })
                continue

            validation = _validate_record(record)
            can_ship = (
                validation["valid"]
                and record.tracking_updated
                and record.status.value == "Generated"
            )
            if can_ship:
                valid_count += 1

            results.append({
                "order_id": oid, "tracking_number": record.tracking_number, "tracking_url": None,
                "carrier": record.carrier_used, "validation_passed": validation["valid"],
                "validation_checks": validation["checks"], "warnings": validation["warnings"],
                "can_ship": can_ship,
            })

        logger.info("Validation: %d/%d orders valid", valid_count, len(order_ids))
        return {"total_checked": len(order_ids), "valid_for_shipment": valid_count, "results": results}

    async def _confirm_shipments_batch(
        self, batch_id: str, orders_to_ship: List[Dict], user_id: int
    ) -> None:
        """Background task: confirm each shipment via Mirakl, stream SSE
        progress after every order, then move record to shipments table."""
        from app.core.database import SessionLocal

        db = SessionLocal()
        total = len(orders_to_ship)
        success_count = failed_count = processed_count = 0

        logger.info("Batch %s: starting confirmation for %d orders", batch_id, len(orders_to_ship))

        # Broadcast initial event
        await sse_manager.broadcast(batch_id, {
            "event": "shipment_start",
            "batch_id": batch_id,
            "total": total,
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "status": "processing",
        })

        try:
            for order_data in orders_to_ship:
                oid = order_data["order_id"]
                try:
                    result = mirakl_shipment_service.confirm_shipment(oid)
                    record = db.query(TrackingUpdate).filter(
                        TrackingUpdate.order_id == oid,
                        TrackingUpdate.user_id == user_id,
                    ).first()

                    if result["success"]:
                        if record:
                            self._move_to_shipments(db, record, batch_id, success=True)
                        success_count += 1
                        logger.info("Batch %s: confirmed order %s", batch_id, oid)
                    else:
                        if record:
                            self._move_to_shipments(db, record, batch_id, success=False, error=result.get("error"))
                        failed_count += 1
                        logger.error(
                            "Batch %s: confirmation failed for %s – %s",
                            batch_id, oid, result.get("error"),
                        )

                    processed_count += 1
                    await sse_manager.broadcast(batch_id, {
                        "event": "shipment_update",
                        "batch_id": batch_id,
                        "order_id": oid,
                        "success": result["success"],
                        "error": result.get("error") if not result["success"] else None,
                        "processed": processed_count,
                        "total": total,
                        "successful": success_count,
                        "failed": failed_count,
                        "progress": round(processed_count / total * 100, 2),
                    })

                except Exception as exc:
                    logger.error(
                        "Batch %s: exception for order %s – %s", batch_id, oid, exc, exc_info=True
                    )
                    failed_count += 1
                    processed_count += 1
                    record = db.query(TrackingUpdate).filter(
                        TrackingUpdate.order_id == oid, TrackingUpdate.user_id == user_id
                    ).first()
                    if record:
                        self._move_to_shipments(db, record, batch_id, success=False, error=str(exc))

                    await sse_manager.broadcast(batch_id, {
                        "event": "shipment_update",
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

                await asyncio.sleep(0.2)

            batch = db.query(ShipmentBatch).filter(ShipmentBatch.batch_id == batch_id).first()
            if batch:
                batch.status = ShipmentStatusEnum.COMPLETED
                batch.completed_at = datetime.utcnow()
                db.commit()

            logger.info("Batch %s done: ok=%d fail=%d", batch_id, success_count, failed_count)

            # Add cache invalidation before closing db:
            dashboard_service = DashboardService(db)
            await dashboard_service.invalidate_cache(user_id)
            logger.info(f"Dashboard cache invalidated for user {user_id}")

            # Broadcast completion
            await sse_manager.broadcast(batch_id, {
                "event": "shipment_complete",
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

    def _move_to_shipments(
        self,
        db: Session,
        record: TrackingUpdate,
        batch_id: str,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Archive a TrackingUpdate as a Shipment record and update batch counters."""
        db.add(Shipment(
            user_id=record.user_id, batch_id=batch_id, order_id=record.order_id,
            commercial_id=record.commercial_id, process_id=record.process_id,
            order_state="SHIPPED", order_date=record.order_date,
            campaign_number=record.campaign_number, ean_code=record.ean_code,
            tracking_number=record.tracking_number, carrier_used=record.carrier_used,
            tracking_url="", shipment_confirmed=success,
            shipment_date=datetime.utcnow() if success else None,
            shipment_status=ShipmentStatusEnum.COMPLETED if success else ShipmentStatusEnum.FAILED,
            original_tracking_id=record.id, error_message=error,
        ))
        db.delete(record)

        batch = db.query(ShipmentBatch).filter(ShipmentBatch.batch_id == batch_id).first()
        if batch:
            batch.processed_orders += 1
            if success:
                batch.successful += 1
            else:
                batch.failed += 1
            if batch.processed_orders >= batch.total_orders:
                batch.status = ShipmentStatusEnum.COMPLETED
                batch.completed_at = datetime.utcnow()

        db.commit()
        logger.debug("Moved order %s to shipments (success=%s)", record.order_id, success)

    @staticmethod
    def _parse_date_range(start_date: str, end_date: str):
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            return start, end
        except ValueError:
            raise ValidationException("Invalid date format. Use YYYY-MM-DD")

    @staticmethod
    def _generate_tracking_url(record: TrackingUpdate) -> Optional[str]:
        """Deprecated – tracking URL is no longer sent to Mirakl."""
        return None
