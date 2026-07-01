# app/services/dashboard_service.py
import calendar
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.redis_dashboard import redis_dashboard
from app.models import OrderProcess, Shipment, TrackingUpdate
from app.services.srp.service import srp_service

logger = logging.getLogger(__name__)

class DashboardService:
    """Dashboard service with Redis caching."""

    def __init__(self, db: Session):
        self.db = db

    async def get_full_dashboard(self, user_id: int) -> Dict[str, Any]:
        """Get complete dashboard data with Redis caching."""

        # Try Redis cache first
        cached = await redis_dashboard.get_cached_dashboard(user_id)
        if cached:
            logger.debug(f"  Returning CACHED dashboard data for user {user_id}")
            return cached

        logger.debug(f"Cache MISS for user {user_id}, calculating fresh data...")

        # Calculate fresh data
        data = await self._calculate_dashboard_data(user_id)

        # Store in Redis cache
        await redis_dashboard.cache_dashboard(user_id, data)

        return data

    async def _calculate_dashboard_data(self, user_id: int) -> Dict[str, Any]:
        """Calculate dashboard data (separate method for caching)."""
        today = date.today()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())

        # ========================================
        # TOTAL LABELS - Count ALL label generations ever made
        # ========================================
        # Labels from tracking_updates table (may be archived/moved)
        total_labels_tracking = self.db.query(func.count(TrackingUpdate.id)).filter(
            TrackingUpdate.user_id == user_id,
            TrackingUpdate.label_generated == True
        ).scalar() or 0

        # Labels from shipments table (confirmed shipments)
        total_labels_shipments = self.db.query(func.count(Shipment.id)).filter(
            Shipment.user_id == user_id
        ).scalar() or 0

        total_labels = total_labels_tracking + total_labels_shipments

        # ========================================
        # TOTAL TRACKING UPDATES - Count tracking updates sent to Mirakl
        # ========================================
        # Tracking updates from tracking_updates table
        total_tracking_tracking = self.db.query(func.count(TrackingUpdate.id)).filter(
            TrackingUpdate.user_id == user_id,
            TrackingUpdate.tracking_updated == True
        ).scalar() or 0

        # All shipments had tracking updated before being moved
        total_tracking_shipments = self.db.query(func.count(Shipment.id)).filter(
            Shipment.user_id == user_id
        ).scalar() or 0

        total_tracking = total_tracking_tracking + total_tracking_shipments

        # ========================================
        # TOTAL SHIPMENTS - Count confirmed shipments
        # ========================================
        total_shipments = self.db.query(func.count(Shipment.id)).filter(
            Shipment.user_id == user_id,
            Shipment.shipment_confirmed == True
        ).scalar() or 0

        # ========================================
        # TODAY'S LABELS - Labels generated today
        # ========================================
        # Labels generated today from tracking_updates
        today_labels_tracking = self.db.query(func.count(TrackingUpdate.id)).filter(
            TrackingUpdate.user_id == user_id,
            TrackingUpdate.label_generated == True,
            TrackingUpdate.created_at >= today_start,
            TrackingUpdate.created_at <= today_end
        ).scalar() or 0

        # Shipments created today (moved today after label generation)
        today_labels_shipments = self.db.query(func.count(Shipment.id)).filter(
            Shipment.user_id == user_id,
            Shipment.created_at >= today_start,
            Shipment.created_at <= today_end
        ).scalar() or 0

        today_labels = today_labels_tracking + today_labels_shipments

        # ========================================
        # TODAY'S TRACKING UPDATES
        # ========================================
        # Tracking updates done today
        today_tracking_tracking = self.db.query(func.count(TrackingUpdate.id)).filter(
            TrackingUpdate.user_id == user_id,
            TrackingUpdate.tracking_updated == True,
            TrackingUpdate.updated_at >= today_start,
            TrackingUpdate.updated_at <= today_end
        ).scalar() or 0

        # Shipments created today (moved today after tracking update)
        today_tracking_shipments = self.db.query(func.count(Shipment.id)).filter(
            Shipment.user_id == user_id,
            Shipment.created_at >= today_start,
            Shipment.created_at <= today_end
        ).scalar() or 0

        today_tracking = today_tracking_tracking + today_tracking_shipments

        # ========================================
        # TODAY'S SHIPMENTS
        # ========================================
        today_shipments = self.db.query(func.count(Shipment.id)).filter(
            Shipment.user_id == user_id,
            Shipment.shipment_confirmed == True,
            Shipment.shipment_date >= today_start,
            Shipment.shipment_date <= today_end
        ).scalar() or 0

        # ... rest of the code remains the same ...

        # Pending processes (still in progress)
        pending = self.db.query(OrderProcess).filter(
            OrderProcess.user_id == user_id,
            OrderProcess.status.in_(["Pending", "Processing"])
        ).count()

        # Get chart data for last 6 months
        months, labels_data, tracking_data, shipments_data = await self._get_chart_data(user_id)

        # Check SRP health
        srp_healthy = srp_service.is_alive()

        # Get greeting
        greeting = self._get_greeting()

        # Calculate percentages for "change" indicators (compared to yesterday)
        yesterday_start = datetime.combine(today - timedelta(days=1), datetime.min.time())
        yesterday_end = datetime.combine(today - timedelta(days=1), datetime.max.time())

        # Yesterday's labels
        yesterday_labels_tracking = self.db.query(func.count(TrackingUpdate.id)).filter(
            TrackingUpdate.user_id == user_id,
            TrackingUpdate.label_generated == True,
            TrackingUpdate.created_at >= yesterday_start,
            TrackingUpdate.created_at <= yesterday_end
        ).scalar() or 0

        yesterday_labels_shipments = self.db.query(func.count(Shipment.id)).filter(
            Shipment.user_id == user_id,
            Shipment.created_at >= yesterday_start,
            Shipment.created_at <= yesterday_end
        ).scalar() or 0

        yesterday_labels = yesterday_labels_tracking + yesterday_labels_shipments

        # Yesterday's tracking
        yesterday_tracking_tracking = self.db.query(func.count(TrackingUpdate.id)).filter(
            TrackingUpdate.user_id == user_id,
            TrackingUpdate.tracking_updated == True,
            TrackingUpdate.updated_at >= yesterday_start,
            TrackingUpdate.updated_at <= yesterday_end
        ).scalar() or 0

        yesterday_tracking_shipments = self.db.query(func.count(Shipment.id)).filter(
            Shipment.user_id == user_id,
            Shipment.created_at >= yesterday_start,
            Shipment.created_at <= yesterday_end
        ).scalar() or 0

        yesterday_tracking = yesterday_tracking_tracking + yesterday_tracking_shipments

        # Yesterday's shipments
        yesterday_shipments = self.db.query(func.count(Shipment.id)).filter(
            Shipment.user_id == user_id,
            Shipment.shipment_confirmed == True,
            Shipment.shipment_date >= yesterday_start,
            Shipment.shipment_date <= yesterday_end
        ).scalar() or 0

        # Calculate changes
        labels_change = self._calculate_change(today_labels, yesterday_labels)
        tracking_change = self._calculate_change(today_tracking, yesterday_tracking)
        shipments_change = self._calculate_change(today_shipments, yesterday_shipments)

        return {
            "stats": {
                # Total counts (all time)
                "total_labels": total_labels,
                "total_tracking": total_tracking,
                "total_shipments": total_shipments,

                # Today's counts
                "today_labels": today_labels,
                "today_tracking": today_tracking,
                "today_shipments": today_shipments,

                # Change percentages
                "labels_change": labels_change,
                "tracking_change": tracking_change,
                "shipments_change": shipments_change,

                # Other stats
                "pending_processes": pending,
                "system_health": "Healthy" if srp_healthy else "Offline"
            },
            "charts": {
                "labels": {
                    "months": months,
                    "data": labels_data,
                    "total": sum(labels_data)
                },
                "tracking": {
                    "months": months,
                    "data": tracking_data,
                    "total": sum(tracking_data)
                },
                "shipments": {
                    "months": months,
                    "data": shipments_data,
                    "total": sum(shipments_data)
                }
            },
            "quick_actions": [
                {"title": "Generate Labels", "description": "Generate shipping labels", "icon": "label"},
                {"title": "Update Tracking", "description": "Update tracking numbers", "icon": "tracking"},
                {"title": "Confirm Shipments", "description": "Confirm shipments", "icon": "shipment"}
            ],
            "user": {
                "greeting": f"{greeting}!",
                "system_health": "Healthy" if srp_healthy else "Offline"
            }
        }

    def _calculate_change(self, today: int, yesterday: int) -> str:
        """Calculate percentage change between today and yesterday."""
        if yesterday == 0:
            if today > 0:
                return "+100%"
            return "0%"

        change = ((today - yesterday) / yesterday) * 100
        if change > 0:
            return f"+{change:.1f}%"
        elif change < 0:
            return f"{change:.1f}%"
        else:
            return "0%"

    async def _get_chart_data(self, user_id: int) -> Tuple[List[str], List[int], List[int], List[int]]:
        """Get monthly chart data for last 6 months."""
        today = datetime.utcnow()
        months = []
        labels_data = []
        tracking_data = []
        shipments_data = []

        # Get last 6 months
        for i in range(5, -1, -1):
            # Calculate month start and end
            month_date = today - timedelta(days=30 * i)
            month_name = calendar.month_abbr[month_date.month]
            months.append(month_name)

            # Month range
            month_start = datetime(month_date.year, month_date.month, 1)
            if month_date.month == 12:
                month_end = datetime(month_date.year + 1, 1, 1)
            else:
                month_end = datetime(month_date.year, month_date.month + 1, 1)

            # Labels generated in this month (from both tables)
            labels_tracking = self.db.query(func.count(TrackingUpdate.id)).filter(
                TrackingUpdate.user_id == user_id,
                TrackingUpdate.label_generated == True,
                TrackingUpdate.created_at >= month_start,
                TrackingUpdate.created_at < month_end
            ).scalar() or 0

            labels_shipments = self.db.query(func.count(Shipment.id)).filter(
                Shipment.user_id == user_id,
                Shipment.created_at >= month_start,
                Shipment.created_at < month_end
            ).scalar() or 0

            labels_count = labels_tracking + labels_shipments
            labels_data.append(labels_count)

            # Tracking updates in this month (from both tables)
            tracking_tracking = self.db.query(func.count(TrackingUpdate.id)).filter(
                TrackingUpdate.user_id == user_id,
                TrackingUpdate.tracking_updated == True,
                TrackingUpdate.updated_at >= month_start,
                TrackingUpdate.updated_at < month_end
            ).scalar() or 0

            # All shipments created in this month had tracking updated before being moved
            tracking_shipments = self.db.query(func.count(Shipment.id)).filter(
                Shipment.user_id == user_id,
                Shipment.created_at >= month_start,
                Shipment.created_at < month_end
            ).scalar() or 0

            tracking_count = tracking_tracking + tracking_shipments
            tracking_data.append(tracking_count)

            # Shipments in this month (by shipment_date)
            shipments_count = self.db.query(func.count(Shipment.id)).filter(
                Shipment.user_id == user_id,
                Shipment.shipment_confirmed == True,
                Shipment.shipment_date >= month_start,
                Shipment.shipment_date < month_end
            ).scalar() or 0
            shipments_data.append(shipments_count)

        return months, labels_data, tracking_data, shipments_data

    def _get_greeting(self) -> str:
        """Get time-based greeting."""
        hour = datetime.utcnow().hour
        if hour < 12:
            return "Good morning"
        elif hour < 18:
            return "Good afternoon"
        return "Good evening"

    async def invalidate_cache(self, user_id: int):
        """Invalidate dashboard cache when data changes"""
        await redis_dashboard.invalidate_dashboard(user_id)
