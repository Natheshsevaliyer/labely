"""
Order service – label generation, process tracking, and PDF report building.

Design notes
------------
* OrderService owns the label-generation workflow end-to-end.
* Heavy PDF work is delegated to pdf_report_service / helpers/pdf_builder.
* Carrier detection is centralised in helpers/carrier.py.
* Pagination is centralised in helpers/pagination.py.
* All background tasks open their own DB session and close it in a finally block.
"""
import asyncio
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import OrderProcess, TrackingStatusEnum, TrackingUpdate, Shipment

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.exceptions import (
    NotFoundException,
    ServiceUnavailableException,
    ValidationException,
)
from app.core.redis_dashboard import redis_dashboard
from app.core.redis_process import redis_process
from app.models import OrderProcess, TrackingStatusEnum, TrackingUpdate
from app.services.base import BaseService
from app.services.dashboard_service import DashboardService
from app.services.file_service import file_service
from app.services.helpers.carrier import detect_carrier_from_address
from app.services.helpers.pagination import build_page_response
from app.services.helpers.pdf_builder import build_interleaved_pdf, load_logo
from app.services.mirakl.order_service import mirakl_order_service
from app.services.pdf_report_service import pdf_report_service
from app.services.srp.async_srp_service import async_srp_service
from app.services.srp.service import srp_service
from app.services.sse_manager import sse_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ELIGIBLE_STATES = {"SHIPPING", "WAITING_SHIPMENT"}
PROCESS_CLEANUP_HOURS = 1
CLEANUP_INTERVAL_SECONDS = 3600


# ---------------------------------------------------------------------------
# Helper – order filtering
# ---------------------------------------------------------------------------

def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse a YYYY-MM-DD date string; return None on failure."""
    try:
        return datetime.strptime(date_str.split("T")[0], "%Y-%m-%d")
    except (ValueError, AttributeError):
        return None


def _is_order_eligible(info: Dict[str, Any], srp: str) -> bool:
    """Return True if the order matches the SRP and is in an eligible state."""
    return (
        info.get("carrier_manager") == srp
        and info.get("order_state") in ELIGIBLE_STATES
        and info.get("can_shop_ship", False)
    )


def _filter_orders(
    raw_orders: List[Dict],
    srp: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict]:
    """
    Filter and sort Mirakl raw orders.

    If start_date / end_date are provided the order date is also checked.
    Returns extracted order-info dicts sorted newest-first.
    """
    start = _parse_date(start_date) if start_date else None
    end = (
        _parse_date(end_date).replace(hour=23, minute=59, second=59)
        if end_date
        else None
    )

    filtered: List[Dict] = []

    for order in raw_orders:
        info = mirakl_order_service.extract_order_info(order)

        if not _is_order_eligible(info, srp):
            continue

        if start and end:
            order_date = _parse_date(info.get("order_date", ""))
            if order_date is None or not (start <= order_date <= end):
                continue

        filtered.append(info)

    filtered.sort(key=lambda x: x.get("order_date", ""), reverse=True)
    logger.info(
        "Filtered %d/%d orders for SRP=%s%s",
        len(filtered),
        len(raw_orders),
        srp,
        f" [{start_date} → {end_date}]" if start_date else "",
    )
    return filtered


# ---------------------------------------------------------------------------
# OrderService
# ---------------------------------------------------------------------------

class OrderService(BaseService[OrderProcess]):
    """Orchestrates label generation, SRP calls, PDF reports, and process tracking."""

    def __init__(self, db: Session) -> None:
        super().__init__(OrderProcess, db)
        self.active_processes: Dict[str, Any] = {}
        self._start_cleanup_thread()

    # ------------------------------------------------------------------
    # Cleanup thread
    # ------------------------------------------------------------------

    def _start_cleanup_thread(self) -> None:
        """Start a daemon thread that periodically removes completed processes from memory."""
        def _loop():
            while True:
                self._cleanup_old_processes()
                time.sleep(CLEANUP_INTERVAL_SECONDS)

        thread = threading.Thread(target=_loop, daemon=True, name="process-cleanup")
        thread.start()
        logger.debug("Process cleanup thread started")

    def _cleanup_old_processes(self) -> None:
        """Remove processes older than PROCESS_CLEANUP_HOURS from the in-memory store."""
        now = datetime.now(timezone.utc)
        cutoff = timedelta(hours=PROCESS_CLEANUP_HOURS)
        to_remove = [
            pid
            for pid, data in self.active_processes.items()
            if data.get("completed_at")
            and now - datetime.fromisoformat(data["completed_at"]).replace(tzinfo=timezone.utc) > cutoff
        ]
        for pid in to_remove:
            del self.active_processes[pid]
            logger.info("Evicted completed process %s from memory", pid)

# --- ADD THIS METHOD INSIDE THE OrderService CLASS ---
    async def get_unified_sales(self, user_id: int) -> List[Dict[str, Any]]:
        # Querying both tables
        active_tracking = self.db.query(TrackingUpdate).filter(TrackingUpdate.user_id == user_id).all()
        finished_shipments = self.db.query(Shipment).filter(Shipment.user_id == user_id).all()

        unified_list = []
        for track in active_tracking:
            unified_list.append({
                "sale_id": track.commercial_id or "N/A",
                "sale_date": track.order_date,
                "carrier": track.carrier_used or "Unknown",
                "order_id": track.order_id,
                "status": "In Progress"
            })
        for ship in finished_shipments:
            unified_list.append({
                "sale_id": ship.commercial_id or "N/A",
                "sale_date": ship.order_date,
                "carrier": ship.carrier_used or "Unknown",
                "order_id": ship.order_id,
                "status": "Shipped"
            })
        
        unified_list.sort(key=lambda x: x["sale_date"] if x["sale_date"] else datetime.min, reverse=True)
        return unified_list
    # ------------------------------------------------------------------
    # Public API – listing
    # ------------------------------------------------------------------

    async def get_mirakl_orders_with_status(
        self,
        user_id: int,
        srp: str,
        page: int = 1,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Return paginated SHIPPING orders for *srp* enriched with label-generation status."""
        logger.info("Fetching Mirakl orders for user=%d srp=%s", user_id, srp)

        raw_orders = mirakl_order_service.fetch_orders_with_filters(
            carrier_manager=srp, order_state="SHIPPING", max=100
        )

        if not raw_orders:
            logger.info("No orders returned from Mirakl for srp=%s", srp)
            return build_page_response([], 0, page, limit, extra={"summary": _empty_summary(srp)})

        order_infos = [mirakl_order_service.extract_order_info(o) for o in raw_orders]
        # Remove invalid items
        order_infos = [
            item for item in order_infos
            if isinstance(item, dict)
        ]

        order_infos.sort(
            key=lambda x: x.get("order_date", ""),
            reverse=True
        )
        order_ids = [o["order_id"] for o in order_infos]
        tracking_map = self._build_tracking_map(user_id, order_ids)

        items = [self._enrich_order_with_tracking(info, tracking_map) for info in order_infos]

        labeled = sum(1 for i in items if i["label_generated"])
        label_count = sum(i["label_generated_count"] for i in items)

        total = len(items)
        offset = (page - 1) * limit
        paginated = items[offset: offset + limit]

        return build_page_response(
            paginated,
            total,
            page,
            limit,
            extra={
                "summary": {
                    "total_orders": total,
                    "shipping_orders": total,
                    "labeled_orders": labeled,
                    "total_label_count": label_count,
                    "srp_filter": srp,
                }
            },
        )

    def _build_tracking_map(self, user_id: int, order_ids: List[str]) -> Dict[str, Any]:
        records = self.db.query(TrackingUpdate).filter(
            TrackingUpdate.order_id.in_(order_ids),
            TrackingUpdate.user_id == user_id,
        ).all()
        return {
            r.order_id: {
                "label_generated": r.label_generated,
                "label_generated_count": r.label_generated_count or 0,
                "tracking_number": r.tracking_number,
                "last_generated_at": r.updated_at.isoformat() if r.updated_at else None,
                "status": r.status.value if r.status else "Unknown",
            }
            for r in records
        }

    @staticmethod
    def _enrich_order_with_tracking(info: Dict, tracking_map: Dict) -> Dict:
        oid = info["order_id"]
        tracking = tracking_map.get(oid, {})
        lines = info.get("order_lines", [])
        return {
            "order_id": oid,
            "order_date": info.get("order_date", ""),
            "campaign_number": lines[0].get("campaign_number", "") if lines else "",
            "order_state": info.get("order_state", ""),
            "commercial_id": info.get("commercial_id", ""),
            "customer_email": info.get("customer_email", ""),
            "label_generated": tracking.get("label_generated", False),
            "label_generated_count": tracking.get("label_generated_count", 0),
            "tracking_number": tracking.get("tracking_number"),
            "last_generated_at": tracking.get("last_generated_at"),
            "status": tracking.get("status", "Not Generated"),
        }

    # ------------------------------------------------------------------
    # Public API – label generation entry-point
    # ------------------------------------------------------------------

    async def generate_labels(
        self,
        user_id: int,
        srp: str,
        quantity: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        order_id: Optional[str] = None,
        label_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Route to the correct generation strategy:

        * ``order_id + label_count`` → multi-copy (one SRP call, N PDF copies)
        * ``quantity``               → quantity-based (last {settings.MIRAKL_QUANTITY_FETCH_DAYS} days)
        * ``start_date + end_date``  → date-range
        """
        if order_id and label_count:
            if not (1 <= label_count <= 100):
                raise ValidationException("label_count must be between 1 and 100")
            logger.info(
                "Multi-copy request – user=%d srp=%s order=%s count=%d",
                user_id, srp, order_id, label_count,
            )
            return await self._generate_multi_copy_labels(user_id, srp, order_id, label_count)

        if quantity is not None:
            if not (1 <= quantity <= 100):
                raise ValidationException("quantity must be between 1 and 100")
            request_method = "quantity"
            logger.info("Quantity-based request – user=%d srp=%s qty=%d", user_id, srp, quantity)
        elif start_date and end_date:
            request_method = "date_range"
            logger.info(
                "Date-range request – user=%d srp=%s [%s → %s]",
                user_id, srp, start_date, end_date,
            )
            try:
                datetime.strptime(start_date, "%Y-%m-%d")
                datetime.strptime(end_date, "%Y-%m-%d")
            except ValueError:
                raise ValidationException("Invalid date format. Use YYYY-MM-DD")
        else:
            raise ValidationException("Provide either 'quantity' or both 'start_date' and 'end_date'")

        self._assert_srp_alive()

        # Determine Mirakl date window
        if request_method == "quantity":
            mirakl_end = datetime.now().strftime("%Y-%m-%d")
            mirakl_start = (datetime.now() - timedelta(days=settings.MIRAKL_QUANTITY_FETCH_DAYS)).strftime("%Y-%m-%d")
        else:
            mirakl_start, mirakl_end = start_date, end_date

        logger.info("Fetching Mirakl orders [%s → %s]", mirakl_start, mirakl_end)
        raw_orders = mirakl_order_service.fetch_orders(mirakl_start, mirakl_end)

        if not raw_orders:
            logger.warning("No orders returned from Mirakl for the date range")
            return _no_orders_response(request_method, srp, quantity, start_date, end_date)

        filtered = _filter_orders(
            raw_orders, srp,
            start_date if request_method == "date_range" else None,
            end_date if request_method == "date_range" else None,
        )

        orders_to_process = filtered[:quantity] if request_method == "quantity" else filtered

        if not orders_to_process:
            logger.warning("No eligible orders found for srp=%s", srp)
            return _no_eligible_response(request_method, srp, quantity, start_date, end_date)

        # Create DB process record
        process = self.create(
            user_id=user_id,
            srp=srp,
            quantity=quantity or len(orders_to_process),
            status="Processing",
            total_orders=len(orders_to_process),
        )

        redis_payload = {
            "status": "processing",
            "total": len(orders_to_process),
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "srp": srp,
            "request_method": request_method,
            "requested_quantity": quantity,
            "requested_start_date": start_date,
            "requested_end_date": end_date,
        }
        await redis_process.create_process(process.id, user_id, redis_payload)

        self.active_processes[str(process.id)] = {
            **redis_payload,
            "process_id": process.id,
            "results": [],
        }

        asyncio.create_task(
            self._process_labels_async(process.id, orders_to_process, user_id)
        )
        logger.info("Process %d created; background task queued (%d orders)", process.id, len(orders_to_process))

        return {
            "success": True,
            "message": (
                f"Started processing {len(orders_to_process)} orders for SRP: {srp}"
                + (f" (quantity: {quantity})" if request_method == "quantity" else f" [{start_date} → {end_date}]")
            ),
            "process_id": process.id,
            "total_orders": len(orders_to_process),
            "successful": 0,
            "failed": 0,
            "request_method": request_method,
            "requested_srp": srp,
            "requested_quantity": quantity,
            "requested_start_date": start_date,
            "requested_end_date": end_date,
        }

    # ------------------------------------------------------------------
    # Multi-copy generation
    # ------------------------------------------------------------------

    async def _generate_multi_copy_labels(
        self, user_id: int, srp: str, order_id: str, label_count: int
    ) -> Dict[str, Any]:
        """Call SRP once and duplicate the resulting PDF *label_count* times."""
        self._assert_srp_alive()

        mirakl_order = mirakl_order_service.fetch_single_order(order_id)
        if not mirakl_order:
            logger.warning("Multi-copy: order %s not found in Mirakl", order_id)
            return _multi_copy_failure(order_id, srp, label_count, f"Order {order_id} not found in Mirakl")

        info = mirakl_order_service.extract_order_info(mirakl_order)

        if info.get("carrier_manager") != srp:
            return _multi_copy_failure(
                order_id, srp, label_count,
                f"Order {order_id} belongs to carrier '{info.get('carrier_manager')}', not '{srp}'",
            )

        if info.get("order_state") not in ELIGIBLE_STATES or not info.get("can_shop_ship", False):
            return _multi_copy_failure(
                order_id, srp, label_count,
                f"Order {order_id} is not in an eligible state (current: {info.get('order_state')})",
            )

        process = self.create(
            user_id=user_id,
            srp=srp,
            quantity=label_count,
            status="Processing",
            total_orders=1,
            request_method="multi_copy",
        )

        await redis_process.create_process(process.id, user_id, {
            "status": "processing",
            "total": label_count,
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "srp": srp,
            "request_method": "multi_copy",
            "requested_order_id": order_id,
            "requested_label_count": label_count,
        })

        asyncio.create_task(
            self._process_multi_copy_background(process.id, info, label_count, user_id, srp)
        )

        return {
            "success": True,
            "message": f"Generating {label_count} label copies for order {order_id}",
            "process_id": process.id,
            "total_orders": 1,
            "total_copies": label_count,
            "successful": 0,
            "failed": 0,
            "request_method": "multi_copy",
            "requested_srp": srp,
            "requested_order_id": order_id,
            "requested_label_count": label_count,
        }

    async def _process_multi_copy_background(
        self,
        process_id: int,
        order_info: Dict[str, Any],
        label_count: int,
        user_id: int,
        srp: str,
    ) -> None:
        """Background: call SRP once then duplicate label PDF *label_count* times."""
        from PyPDF2 import PdfReader, PdfWriter  # type: ignore

        db = SessionLocal()
        order_id = order_info["order_id"]

        try:
            process = db.query(OrderProcess).filter(OrderProcess.id == process_id).first()
            if not process:
                logger.error("Multi-copy background: process %d not found", process_id)
                return

            # Broadcast initial progress
            await sse_manager.broadcast_progress(
                process_id=str(process_id),
                processed=0,
                total=label_count,
                successful=0,
                failed=0,
                status="processing",
            )

            # --- SRP call ---
            logger.info("Multi-copy [%d]: calling SRP for order %s", process_id, order_id)

            # Update progress - SRP call started
            await sse_manager.broadcast_progress(
                process_id=str(process_id),
                processed=0,
                total=label_count,
                successful=0,
                failed=0,
                status="processing",
            )

            srp_results = await async_srp_service.generate_labels_batch([order_id])
            srp_data = srp_results[0] if srp_results else {}

            if not srp_data.get("success"):
                error = srp_data.get("error", "SRP API failed")
                logger.error("Multi-copy [%d]: SRP failed for %s – %s", process_id, order_id, error)

                # Broadcast failure
                await sse_manager.broadcast_progress(
                    process_id=str(process_id),
                    processed=label_count,
                    total=label_count,
                    successful=0,
                    failed=label_count,
                    status="Failed",
                    failed_orders=[{"order_id": order_id, "error": error}]
                )
                await self._fail_process(db, process, process_id, error)
                return

            tracking_number = srp_data.get("tracking_number")
            label_data = srp_data.get("label")

            if not tracking_number or not label_data:
                error = "SRP returned incomplete data (missing tracking number or label)"
                logger.error("Multi-copy [%d]: %s", process_id, error)

                # Broadcast failure
                await sse_manager.broadcast_progress(
                    process_id=str(process_id),
                    processed=label_count,
                    total=label_count,
                    successful=0,
                    failed=label_count,
                    status="Failed",
                    failed_orders=[{"order_id": order_id, "error": error}]
                )
                await self._fail_process(db, process, process_id, error)
                return

            logger.info("Multi-copy [%d]: SRP succeeded – tracking=%s", process_id, tracking_number)

            # Update progress - SRP succeeded, now saving labels
            await sse_manager.broadcast_progress(
                process_id=str(process_id),
                processed=1,
                total=label_count,
                successful=1,
                failed=0,
                status="processing",
            )

            # --- Save original label ---
            original_path = await async_srp_service.save_label_to_file(
                order_number=f"{order_id}_original",
                label_data=label_data,
                process_id=process_id,
            )
            if not original_path:
                error = "Failed to save label PDF"
                logger.error("Multi-copy [%d]: %s", process_id, error)

                # Broadcast failure
                await sse_manager.broadcast_progress(
                    process_id=str(process_id),
                    processed=label_count,
                    total=label_count,
                    successful=0,
                    failed=label_count,
                    status="Failed",
                    failed_orders=[{"order_id": order_id, "error": error}]
                )
                await self._fail_process(db, process, process_id, error)
                return

            # --- Duplicate label N times ---
            label_copies: List[str] = []
            reader = PdfReader(original_path)

            for i in range(label_count):
                copy_path = os.path.join(settings.OUTPUT_FOLDER, f"{order_id}_copy_{i + 1}_{process_id}.pdf")
                writer = PdfWriter()
                for page in reader.pages:
                    writer.add_page(page)
                with open(copy_path, "wb") as fh:
                    writer.write(fh)
                label_copies.append(copy_path)

                # Broadcast progress for each copy
                await sse_manager.broadcast_progress(
                    process_id=str(process_id),
                    processed=i + 1,
                    total=label_count,
                    successful=i + 1,
                    failed=0,
                    status="processing",
                )

            logger.info("Multi-copy [%d]: created %d label copies", process_id, label_count)

            # --- Upsert tracking record ---
            carrier = detect_carrier_from_address(order_info.get("shipping_address", {}))
            country = order_info.get("shipping_address", {}).get("country", "")
            self._upsert_tracking(db, user_id, process_id, order_id, order_info, tracking_number, carrier, country, label_count)

            # --- Generate report and merge ---
            report_path = await self._generate_multi_copy_report(process_id, order_info, tracking_number, label_count)
            labels_only_path = file_service.merge_labels_only(label_copies, str(process_id))

            merged_url: Optional[str] = None
            if report_path:
                merged_filename = f"labels_report_{process_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
                merged_path = os.path.join(settings.OUTPUT_FOLDER, merged_filename)
                if build_interleaved_pdf(merged_path, label_copies, report_path):
                    merged_url = f"/api/v1/download/labels/{process_id}"

            labels_only_url = None
            if labels_only_path:
                labels_only_url = f"/api/v1/download/labels-only/{process_id}?filename={os.path.basename(labels_only_path)}"

            report_url = f"/api/v1/download/report/{process_id}" if report_path and os.path.exists(report_path) else None

            # --- Finalise process ---
            process.status = "Completed"
            process.completed_at = datetime.utcnow()
            process.successful_count = label_count
            process.failed_count = 0
            process.output_url = merged_url
            process.output_file = os.path.basename(merged_url) if merged_url else None
            db.commit()

            await redis_process.update_process(process_id, {
                "status": "Completed",
                "processed": label_count,
                "successful": label_count,
                "failed": 0,
                "completed_at": process.completed_at.isoformat(),
                "download_url": merged_url,
                "labels_only_url": labels_only_url,
                "report_url": report_url,
                "label_count": label_count,
            })

            await redis_dashboard.invalidate_dashboard(user_id)

            dashboard_service = DashboardService(db)
            await dashboard_service.invalidate_cache(user_id)

            # Broadcast final completion with URLs
            await sse_manager.broadcast_progress(
                process_id=str(process_id),
                processed=label_count,
                total=label_count,
                successful=label_count,
                failed=0,
                status="Completed",
                download_url=merged_url,
                labels_only_url=labels_only_url,
                report_url=report_url,
            )

            logger.info("Multi-copy [%d]: completed – %d copies generated", process_id, label_count)

        except Exception as exc:
            logger.error("Multi-copy [%d]: unhandled error – %s", process_id, exc, exc_info=True)

            # Broadcast error
            await sse_manager.broadcast_progress(
                process_id=str(process_id),
                processed=label_count,
                total=label_count,
                successful=0,
                failed=label_count,
                status="Failed",
                failed_orders=[{"order_id": order_id if 'order_id' in locals() else "unknown", "error": str(exc)}]
            )

            try:
                process = db.query(OrderProcess).filter(OrderProcess.id == process_id).first()
                if process:
                    await self._fail_process(db, process, process_id, str(exc))
            except Exception as inner:
                logger.error("Multi-copy [%d]: could not update failure status – %s", process_id, inner)
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Batch label processing (quantity / date-range)
    # ------------------------------------------------------------------

    async def _process_labels_async(
        self, process_id: int, orders: List[Dict], user_id: int
    ) -> None:
        """Background: send ALL orders to SRP at once (single token), stream
        SSE progress as each label result arrives."""
        logger.info("Batch [%d]: starting – %d orders", process_id, len(orders))
        db = SessionLocal()

        successful_orders: List[Dict] = []
        regenerated_orders: List[Dict] = []
        failed_orders: List[Dict] = []
        label_files: List[str] = []

        try:
            process = db.query(OrderProcess).filter(OrderProcess.id == process_id).first()
            if not process:
                logger.error("Batch [%d]: process not found", process_id)
                return

            # Pre-fetch existing tracking records
            order_ids = [o["order_id"] for o in orders]
            existing = {r.order_id: r for r in db.query(TrackingUpdate).filter(
                TrackingUpdate.order_id.in_(order_ids)
            ).all()}

            # Build a fast order lookup
            order_map = {o["order_id"]: o for o in orders}

            # # Create tracking stubs for new orders
            # new_records: List[TrackingUpdate] = []
            # new_order_ids: set = set()
            # for order in orders:
            #     oid = order["order_id"]
            #     if oid not in existing:
            #         carrier = detect_carrier_from_address(order.get("shipping_address", {}))
            #         rec = TrackingUpdate(
            #             user_id=user_id,
            #             process_id=process_id,
            #             order_id=oid,
            #             commercial_id=order.get("commercial_id", ""),
            #             order_state=order.get("order_state", ""),
            #             order_date=_parse_date(order.get("order_date", "")),
            #             status=TrackingStatusEnum.NOT_YET,
            #             label_generated=False,
            #             tracking_updated=False,
            #             carrier_used=carrier,
            #             created_at=datetime.utcnow(),
            #         )
            #         lines = order.get("order_lines", [])
            #         if lines:
            #             rec.campaign_number = lines[0].get("campaign_number", "")
            #             rec.ean_code = lines[0].get("ean_code", "")
            #         new_records.append(rec)
            #         existing[oid] = rec
            #         new_order_ids.add(oid)

            # if new_records:
            #     db.add_all(new_records)
            #     db.flush()
            #     logger.info("Batch [%d]: created %d tracking stubs", process_id, len(new_records))

            total = len(order_ids)
            success_count = failed_count = processed_count = 0
            db_commit_pending = 0  # commit every N results to reduce DB round-trips

            # Broadcast initial "started" event
            await sse_manager.broadcast_progress(
                process_id=str(process_id), processed=0, total=total,
                successful=0, failed=0, status="processing",
            )

            # ── Single token · all orders · streaming results ─────────────
            # generate_labels_stream fetches ONE token then fires all orders
            # concurrently, yielding each dict as soon as its request finishes.
            logger.info(
                "Batch [%d]: dispatching all %d orders to SRP (single token)", process_id, total
            )
            async for srp_result in async_srp_service.generate_labels_stream(order_ids):

                oid = srp_result["order_number"]

                order = order_map.get(oid)

                if not order:
                    logger.warning(
                        "Batch [%d]: order not found for %s",
                        process_id,
                        oid
                    )

                    failed_count += 1
                    processed_count += 1
                    continue

                # ---------------------------------------------------------
                # SUCCESS
                # ---------------------------------------------------------

                if srp_result.get("success"):

                    tracking_number = srp_result.get("tracking_number")
                    label_data = srp_result.get("label")

                    if not tracking_number or not label_data:

                        logger.warning(
                            "Batch [%d]: missing tracking/label for %s",
                            process_id,
                            oid
                        )

                        failed_orders.append({
                            "order_id": oid,
                            "error": "Missing tracking number or label"
                        })

                        failed_count += 1

                    else:

                        # Save PDF label
                        label_path = await self._save_label(
                            oid,
                            label_data,
                            process_id
                        )

                        if label_path:
                            label_files.append(label_path)

                        carrier = detect_carrier_from_address(
                            order.get("shipping_address", {})
                        )

                        shipping_address = order.get("shipping_address", {})
                        country = shipping_address.get("country", "")

                        existing_tracking = existing.get(oid)

                        # -----------------------------------------
                        # UPDATE EXISTING ORDER
                        # -----------------------------------------

                        if existing_tracking:

                            self._mark_tracking_success(
                                existing_tracking,
                                tracking_number,
                                country
                            )

                            tracking_record = existing_tracking

                        # -----------------------------------------
                        # CREATE NEW ORDER
                        # -----------------------------------------

                        else:

                            lines = order.get("order_lines", [])
                            shipping_address = order.get("shipping_address", {})
                            country = shipping_address.get("country", "")

                            tracking_record = TrackingUpdate(
                                user_id=user_id,
                                process_id=process_id,
                                order_id=oid,
                                commercial_id=order.get("commercial_id", ""),
                                order_state=order.get("order_state", ""),
                                order_date=_parse_date(
                                    order.get("order_date", "")
                                ),
                                status=TrackingStatusEnum.GENERATED,
                                label_generated=True,
                                label_generated_count=1,
                                tracking_number=tracking_number,
                                carrier_used=carrier,
                                country=country,
                                tracking_updated=False,
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow(),
                                campaign_number=(
                                    lines[0].get("campaign_number", "")
                                    if lines else ""
                                ),
                                ean_code=(
                                    lines[0].get("ean_code", "")
                                    if lines else ""
                                ),
                            )

                            db.add(tracking_record)

                            existing[oid] = tracking_record

                        successful_orders.append({
                            "success": True,
                            "order_id": oid,
                            "tracking_number": tracking_number,
                            "generation_count": tracking_record.label_generated_count,
                            "label_path": label_path,
                        })

                        success_count += 1

                        logger.info(
                            "Batch [%d]: label generated for %s",
                            process_id,
                            oid
                        )

                # ---------------------------------------------------------
                # FAILURE
                # ---------------------------------------------------------

                else:

                    error = srp_result.get(
                        "error",
                        "Unknown SRP error"
                    )

                    logger.warning(
                        "Batch [%d]: SRP failed for %s - %s",
                        process_id,
                        oid,
                        error
                    )

                    failed_orders.append({
                        "order_id": oid,
                        "error": error
                    })

                    failed_count += 1

                # ---------------------------------------------------------
                # COMMON PROGRESS
                # ---------------------------------------------------------

                processed_count += 1
                db_commit_pending += 1

                if db_commit_pending >= 10:
                    db.commit()
                    db_commit_pending = 0

                await redis_process.update_process(
                    process_id,
                    {
                        "processed": processed_count,
                        "successful": success_count,
                        "failed": failed_count,
                        "status": "processing",
                    }
                )

                if str(process_id) in self.active_processes:

                    self.active_processes[str(process_id)].update({
                        "processed": processed_count,
                        "successful": success_count,
                        "failed": failed_count,
                    })

                await sse_manager.broadcast_progress(
                    process_id=str(process_id),
                    processed=processed_count,
                    total=total,
                    successful=success_count,
                    failed=failed_count,
                    status="processing",
                )

                logger.info(
                    "Batch [%d]: %.1f%% (%d/%d) ok=%d fail=%d",
                    process_id,
                    processed_count / total * 100,
                    processed_count,
                    total,
                    success_count,
                    failed_count,
                )
            # Final DB commit for any remaining uncommitted rows
            if db_commit_pending:
                db.commit()

            # --- Reports and merge ---
            all_successful = successful_orders + regenerated_orders
            merged_url = await self._generate_reports_and_merge(
                db, process_id, orders, all_successful, label_files
            ) if all_successful else None

            labels_only_url = self._find_labels_only_url(process_id) if all_successful else None
            report_url = self._find_report_url(process_id) if all_successful else None

            # --- Final status ---
            if all_successful and not failed_orders:
                final_status = "Completed"
            elif all_successful:
                final_status = "Partial"
            else:
                final_status = "Failed"

            process.status = final_status
            process.completed_at = datetime.utcnow()
            process.successful_count = len(all_successful)
            process.failed_count = len(failed_orders)
            process.output_url = merged_url
            process.output_file = os.path.basename(merged_url) if merged_url else None

            failed_details = [{"order_id": f["order_id"], "error": f["error"], "is_new": f.get("is_new", False)}
                               for f in failed_orders]

            await redis_process.update_process(process_id, {
                "status": final_status,
                "processed": processed_count,
                "successful": len(all_successful),
                "failed": len(failed_orders),
                "completed_at": process.completed_at.isoformat(),
                "download_url": merged_url,
                "labels_only_url": labels_only_url,
                "report_url": report_url,
            })
            db.commit()

            await redis_dashboard.invalidate_dashboard(user_id)
            # Add cache invalidation for dashboard:
            dashboard_service = DashboardService(db)
            await dashboard_service.invalidate_cache(user_id)
            logger.info(f"Dashboard cache invalidated for user {user_id}")

            await sse_manager.broadcast_progress(
                process_id=str(process_id), processed=processed_count, total=total,
                successful=process.successful_count, failed=process.failed_count,
                status=final_status, download_url=merged_url,
                labels_only_url=labels_only_url, report_url=report_url,
                failed_orders=failed_details,
            )
            await sse_manager.broadcast(
                process_id=str(process_id),
                data={
                    "event": "complete", "message": "Process completed",
                    "status": final_status, "download_url": merged_url,
                    "labels_only_url": labels_only_url, "report_url": report_url,
                    "successful": process.successful_count, "failed": process.failed_count,
                    "total": total, "failed_orders": failed_details,
                },
            )
            logger.info(
                "Batch [%d]: DONE status=%s ok=%d fail=%d",
                process_id, final_status, process.successful_count, process.failed_count,
            )

        except Exception as exc:
            logger.error("Batch [%d]: unhandled error – %s", process_id, exc, exc_info=True)
            await redis_process.update_process(process_id, {"status": "Failed", "error": str(exc)})
        finally:
            db.close()


    # ------------------------------------------------------------------
    # Process status
    # ------------------------------------------------------------------

    async def get_process_status(self, process_id: int, user_id: int) -> Dict[str, Any]:
        """Return current status from Redis (fast) or fall back to DB."""
        redis_status = await redis_process.get_process(process_id)
        if redis_status:
            logger.debug("Process %d status fetched from Redis", process_id)
            return {
                "process_id": redis_status["process_id"],
                "status": redis_status["status"],
                "total": redis_status["total"],
                "successful": redis_status["successful"],
                "failed": redis_status["failed"],
                "download_url": redis_status.get("download_url"),
                "labels_only_url": redis_status.get("labels_only_url"),
                "report_url": redis_status.get("report_url"),
                "created_at": redis_status.get("created_at"),
                "completed_at": redis_status.get("completed_at"),
                "srp": redis_status.get("srp", ""),
                "request_method": redis_status.get("request_method", "quantity"),
                "requested_quantity": redis_status.get("requested_quantity"),
                "requested_start_date": redis_status.get("requested_start_date"),
                "requested_end_date": redis_status.get("requested_end_date"),
            }

        # DB fallback
        process = self.db.query(OrderProcess).filter(
            OrderProcess.id == process_id,
            OrderProcess.user_id == user_id,
        ).first()

        if not process:
            logger.warning("Process %d not found for user %d", process_id, user_id)
            raise NotFoundException("Process not found")

        successful = self.db.query(func.count(TrackingUpdate.id)).filter(
            TrackingUpdate.process_id == process_id,
            TrackingUpdate.label_generated == True,
        ).scalar() or 0

        failed = self.db.query(func.count(TrackingUpdate.id)).filter(
            TrackingUpdate.process_id == process_id,
            TrackingUpdate.label_generated == False,
            TrackingUpdate.error_message.isnot(None),
        ).scalar() or 0

        labels_only_url = self._find_labels_only_url(process_id) if process.status in ("Completed", "Partial") else None
        report_url = self._find_report_url(process_id) if process.status in ("Completed", "Partial") else None

        return {
            "process_id": process.id,
            "status": process.status,
            "total": process.total_orders,
            "successful": successful,
            "failed": failed,
            "download_url": process.output_url,
            "labels_only_url": labels_only_url,
            "report_url": report_url,
            "created_at": process.created_at.isoformat() if process.created_at else None,
            "completed_at": process.completed_at.isoformat() if process.completed_at else None,
            "srp": process.srp,
            "request_method": "quantity",
            "requested_quantity": process.quantity,
            "requested_start_date": None,
            "requested_end_date": None,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _assert_srp_alive(self) -> None:
        if not srp_service.is_alive():
            logger.error("SRP service is unavailable")
            raise ServiceUnavailableException("SRP label service is not available")

    @staticmethod
    async def _save_label(order_id: str, label_data: Any, process_id: int) -> Optional[str]:
        try:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            return await async_srp_service.save_label_to_file(
                order_number=f"{order_id}_{ts}",
                label_data=label_data,
                process_id=process_id,
            )
        except Exception as exc:
            logger.error("Failed to save label for order %s: %s", order_id, exc)
            return None

    @staticmethod
    def _mark_tracking_success(tracking: TrackingUpdate, tracking_number: str, country: Optional[str] = None,) -> None:
        tracking.tracking_number = tracking_number
        tracking.label_generated = True
        tracking.label_generated_count = (tracking.label_generated_count or 0) + 1
        tracking.status = TrackingStatusEnum.GENERATED
        if country:
            tracking.country = country
        tracking.error_message = None
        tracking.updated_at = datetime.utcnow()

    @staticmethod
    def _mark_tracking_failed(tracking: TrackingUpdate, error: str) -> None:
        tracking.error_message = error
        tracking.label_generated = False
        tracking.status = TrackingStatusEnum.NO_LABEL
        tracking.updated_at = datetime.utcnow()

    def _upsert_tracking(
        self,
        db: Session,
        user_id: int,
        process_id: int,
        order_id: str,
        order_info: Dict,
        tracking_number: str,
        carrier: str,
        country: str,
        label_count: int,
    ) -> None:
        existing = db.query(TrackingUpdate).filter(
            TrackingUpdate.order_id == order_id,
            TrackingUpdate.user_id == user_id,
        ).first()

        if existing:
            existing.label_generated_count = (existing.label_generated_count or 0) + label_count
            existing.label_generated = True
            existing.tracking_number = tracking_number
            existing.carrier_used = carrier
            existing.country = country
            existing.status = TrackingStatusEnum.GENERATED
            existing.updated_at = datetime.utcnow()
        else:
            lines = order_info.get("order_lines", [])
            rec = TrackingUpdate(
                user_id=user_id,
                process_id=process_id,
                order_id=order_id,
                commercial_id=order_info.get("commercial_id", ""),
                order_state=order_info.get("order_state", ""),
                order_date=_parse_date(order_info.get("order_date", "")),
                status=TrackingStatusEnum.GENERATED,
                label_generated=True,
                label_generated_count=label_count,
                tracking_number=tracking_number,
                carrier_used=carrier,
                country=country,
                tracking_updated=False,
                created_at=datetime.utcnow(),
                campaign_number=lines[0].get("campaign_number", "") if lines else "",
                ean_code=lines[0].get("ean_code", "") if lines else "",
            )
            db.add(rec)

        db.commit()

    async def _generate_reports_and_merge(
        self,
        db: Session,
        process_id: int,
        orders: List[Dict],
        successful_orders: List[Dict],
        label_files: List[str],
    ) -> Optional[str]:
        """Generate the report PDF and merged interleaved PDF; return download URL or None."""
        try:
            report_path = await self._generate_pdf_report(db, process_id, orders)

            if label_files:
                file_service.merge_labels_only(label_files, str(process_id))

            if report_path and label_files:
                from PyPDF2 import PdfReader  # type: ignore
                report_pages = len(PdfReader(report_path).pages)

                if report_pages == len(label_files):
                    merged_name = f"labels_report_{process_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
                    merged_path = os.path.join(settings.OUTPUT_FOLDER, merged_name)
                    if build_interleaved_pdf(merged_path, label_files, report_path):
                        return f"/api/v1/download/labels/{process_id}"
                else:
                    logger.warning(
                        "Batch [%d]: report pages (%d) ≠ label files (%d) – skipping interleave",
                        process_id, report_pages, len(label_files),
                    )
        except Exception as exc:
            logger.error("Batch [%d]: report/merge failed – %s", process_id, exc, exc_info=True)

        return None

    async def _generate_pdf_report(
        self, db: Session, process_id: int, orders: List[Dict]
    ) -> Optional[str]:
        """Build a per-order-line report PDF and return the file path."""
        try:
            results: List[Dict] = []
            for order in orders:
                oid = order["order_id"]
                tracking = db.query(TrackingUpdate).filter(TrackingUpdate.order_id == oid).first()
                if not (tracking and tracking.label_generated):
                    continue

                for line in order.get("order_lines", []) or [{"sku": "", "quantity": 1}]:
                    results.append({
                        "order_id": oid,
                        "tracking_number": tracking.tracking_number,
                        "status": "success",
                        "error": None,
                        "sku": line.get("sku", ""),
                        "description": line.get("description", "") or line.get("product_title", ""),
                        "quantity": line.get("quantity", 1),
                        "ean_code": line.get("ean_code", tracking.ean_code or ""),
                        "campaign_number": line.get("campaign_number", tracking.campaign_number or ""),
                        "shipping_address": order.get("shipping_address", {}),
                        "generation_count": tracking.label_generated_count or 1,
                    })

            if results:
                logger.info("Batch [%d]: generating PDF report (%d lines)", process_id, len(results))
                return pdf_report_service.create_report(
                    results=results, process_id=str(process_id), orders_data=orders
                )
        except Exception as exc:
            logger.error("Batch [%d]: PDF report generation failed – %s", process_id, exc, exc_info=True)

        return None

    async def _generate_multi_copy_report(
        self,
        process_id: int,
        order_info: Dict[str, Any],
        tracking_number: str,
        label_count: int,
    ) -> Optional[str]:
        """Generate an N-page PDF report (one page per label copy)."""
        from reportlab.lib import colors  # type: ignore
        from reportlab.lib.enums import TA_CENTER, TA_LEFT  # type: ignore
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
        from reportlab.lib.units import inch  # type: ignore
        from reportlab.platypus import (  # type: ignore
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        report_path = os.path.join(settings.OUTPUT_FOLDER, f"report_{process_id}.pdf")
        doc = SimpleDocTemplate(
            report_path, pagesize=A4,
            rightMargin=15, leftMargin=15, topMargin=20, bottomMargin=20,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=14,
                                     alignment=TA_CENTER, spaceAfter=10)
        header_style = ParagraphStyle("Header", parent=styles["Normal"], fontSize=9,
                                      fontName="Helvetica-Bold", alignment=TA_CENTER,
                                      textColor=colors.HexColor("#2c3e50"))
        cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=7,
                                    alignment=TA_LEFT, wordWrap="CJK")

        logo = load_logo()
        order_id = order_info["order_id"]
        order_lines = order_info.get("order_lines", [])
        shipping_addr = self._format_address(order_info.get("shipping_address", {}))

        col_widths = [60, 50, 65, 90, 30, 140, 65, 65]
        header_row = [
            Paragraph(h, header_style)
            for h in ["Order ID", "SKU", "EAN", "Description", "Qty",
                       "Shipping Address", "Tracking #", "Campaign #"]
        ]

        elements = []
        for copy_num in range(1, label_count + 1):
            title_text = f"Order Report – Copy {copy_num} of {label_count}"
            if logo:
                hdr_tbl = Table([[logo, Paragraph(title_text, title_style)]], colWidths=[130, 400])
                hdr_tbl.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ]))
                elements.append(hdr_tbl)
            else:
                elements.append(Paragraph(title_text, title_style))

            elements.append(Spacer(1, 0.1 * inch))
            elements.append(Paragraph(
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  "
                f"Process: #{process_id}  |  Order: {order_id}",
                styles["Normal"],
            ))
            elements.append(Spacer(1, 0.2 * inch))

            rows = [header_row]
            for line in order_lines:
                desc = (line.get("description", "") or line.get("product_title", ""))[:40]
                addr = shipping_addr[:90]
                rows.append([
                    Paragraph(order_id, cell_style),
                    Paragraph(line.get("sku", ""), cell_style),
                    Paragraph(line.get("ean_code", ""), cell_style),
                    Paragraph(desc, cell_style),
                    str(line.get("quantity", 1)),
                    Paragraph(addr, cell_style),
                    Paragraph(tracking_number, cell_style),
                    Paragraph(line.get("campaign_number", ""), cell_style),
                ])

            tbl = Table(rows, colWidths=col_widths, repeatRows=1)
            tbl.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#2c3e50")),
                ("ALIGN", (5, 1), (5, -1), "CENTER"),
            ]))
            elements.append(tbl)

            if copy_num < label_count:
                elements.append(PageBreak())

        doc.build(elements)
        logger.info("Multi-copy report written to %s (%d pages)", report_path, label_count)
        return report_path

    @staticmethod
    def _format_address(address: Dict[str, Any]) -> str:
        if not address or not any(address.values()):
            return "N/A"
        parts = []
        name = " ".join(filter(None, [address.get("firstname"), address.get("lastname")])).strip()
        if name:
            parts.append(name)
        if address.get("company"):
            parts.append(address["company"])
        if address.get("city"):
            parts.append(address["city"])
        if address.get("zip_code"):
            parts.append(address["zip_code"])
        if address.get("country"):
            parts.append(address["country"])
        if address.get("phone"):
            parts.append(f"Tel: {address['phone']}")
        return ", ".join(parts) or "N/A"

    @staticmethod
    async def _fail_process(db: Session, process: OrderProcess, process_id: int, error: str) -> None:
        process.status = "Failed"
        process.error_message = error
        process.completed_at = datetime.utcnow()
        db.commit()
        await redis_process.update_process(process_id, {"status": "Failed", "error": error})

    @staticmethod
    def _find_labels_only_url(process_id: int) -> Optional[str]:
        prefix = f"labels_only_{process_id}_"
        try:
            for fn in sorted(os.listdir(settings.OUTPUT_FOLDER), reverse=True):
                if fn.startswith(prefix) and fn.endswith(".pdf"):
                    return f"/api/v1/download/labels-only/{process_id}?filename={fn}"
        except OSError:
            pass
        return None

    @staticmethod
    def _find_report_url(process_id: int) -> Optional[str]:
        path = os.path.join(settings.OUTPUT_FOLDER, f"report_{process_id}.pdf")
        return f"/api/v1/download/report/{process_id}" if os.path.exists(path) else None


# ---------------------------------------------------------------------------
# Module-level response builders (reduce repetition)
# ---------------------------------------------------------------------------

def _empty_summary(srp: str) -> Dict:
    return {"total_orders": 0, "shipping_orders": 0, "labeled_orders": 0, "total_label_count": 0, "srp_filter": srp}


def _base_response(request_method: str, srp: str, quantity, start_date, end_date) -> Dict:
    return {
        "process_id": None,
        "total_orders": 0,
        "successful": 0,
        "failed": 0,
        "request_method": request_method,
        "requested_srp": srp,
        "requested_quantity": quantity,
        "requested_start_date": start_date,
        "requested_end_date": end_date,
    }


def _no_orders_response(method, srp, qty, sd, ed) -> Dict:
    return {"success": False, "message": "No orders found in date range", **_base_response(method, srp, qty, sd, ed)}


def _no_eligible_response(method, srp, qty, sd, ed) -> Dict:
    suffix = f" in date range {sd} to {ed}" if method == "date_range" else ""
    return {
        "success": False,
        "message": f"No eligible orders found for SRP: {srp}{suffix}",
        **_base_response(method, srp, qty, sd, ed),
    }


def _multi_copy_failure(order_id, srp, label_count, message) -> Dict:
    return {
        "success": False,
        "message": message,
        "process_id": None,
        "total_orders": 1,
        "successful": 0,
        "failed": 1,
        "request_method": "multi_copy",
        "requested_srp": srp,
        "requested_order_id": order_id,
        "requested_label_count": label_count,
    }
