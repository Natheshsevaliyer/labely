from typing import Any, Dict, List, Optional

from .base import BaseSchema


class BulkTrackingUpdateRequest(BaseSchema):
    """Bulk tracking update request schema."""
    order_ids: List[str]
    process_id: Optional[int] = None
    force_update: bool = False

class BulkTrackingUpdateResponse(BaseSchema):
    """Bulk tracking update response schema."""
    success: bool
    message: str
    total_selected: int
    processing: int
    skipped: int
    skipped_details: List[Dict[str, Any]]
    force_update: bool

class ReadyOrderResponse(BaseSchema):
    """Ready order response schema."""
    order_id: str
    order_date: str
    tracking_number: Optional[str] = None
    campaign_number: str
    process_id: Optional[int] = None
    order_state: str
    carrier_manager: Optional[str] = None
    commercial_id: Optional[str] = None
    customer_email: Optional[str] = None
    can_shop_ship: Optional[bool] = False
    label_generated_count: int = 0
    label_status: Optional[str] = None
    tracking_status: str
    status_reason: Optional[str] = None
    can_update: bool
    mirakl_tracking: Optional[str] = None
    mirakl_tracking_url: Optional[str] = None
    mirakl_carrier: Optional[str] = None
    update_attempts: int = 0
    last_attempt: Optional[str] = None

class ReadyOrdersListResponse(BaseSchema):
    """Ready orders list response schema."""
    total: int
    page: int
    limit: int
    pages: int
    has_next: bool
    has_previous: bool
    items: List[ReadyOrderResponse]
    summary: Dict[str, Any]

class TrackingStatusResponse(BaseSchema):
    """Tracking status response schema."""
    process_id: int
    total_orders: int
    labels_generated: int
    tracking_updated: int
    ready_to_update: int
    failed_attempts: int
    statuses: List[Dict[str, Any]]
