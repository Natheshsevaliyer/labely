# app/schemas/dashboard.py
from typing import Any, Dict, List, Optional

from .base import BaseSchema


class DashboardStats(BaseSchema):
    """Dashboard statistics schema."""
    # Total counts
    total_labels: int
    total_tracking: int
    total_shipments: int

    # Today's counts
    today_labels: int
    today_tracking: int
    today_shipments: int

    # Change percentages
    labels_change: str
    tracking_change: str
    shipments_change: str

    # Other stats
    pending_processes: int
    system_health: str

class MonthlyDataPoint(BaseSchema):
    """Monthly data point schema."""
    month: str
    value: int

class ChartData(BaseSchema):
    """Chart data schema."""
    months: List[str]
    data: List[int]
    total: int

class GenerateLabelsChartData(BaseSchema):
    """Generate labels chart data schema."""
    data: List[MonthlyDataPoint]
    total: int
    growth: str

class UpdateTrackingChartData(BaseSchema):
    """Update tracking chart data schema."""
    data: List[MonthlyDataPoint]
    total: int
    growth: str

class ShipmentChartData(BaseSchema):
    """Shipment chart data schema."""
    data: List[MonthlyDataPoint]
    total: int
    growth: str

class AdminQuickAction(BaseSchema):
    """Admin quick action schema."""
    title: str
    description: str
    action_url: str
    icon: Optional[str] = None

class DashboardResponse(BaseSchema):
    """Dashboard response schema."""
    stats: DashboardStats
    quick_actions: List[AdminQuickAction]
    charts: Dict[str, ChartData]  # Will contain 'labels', 'tracking', 'shipments'
    user: Dict[str, str]

class SimpleDashboardResponse(BaseSchema):
    """Simple dashboard response schema."""
    stats: Dict[str, Any]
    charts: Dict[str, ChartData]
    quick_actions: List[Dict[str, str]]
    user: Dict[str, str]
