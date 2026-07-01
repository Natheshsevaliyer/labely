from typing import Any, Dict, List, Optional

from .base import BaseSchema


class ShipmentValidationRequest(BaseSchema):
    """Shipment validation request schema."""
    order_ids: List[str]
    force_confirm: bool = False

class ShipmentValidationResult(BaseSchema):
    """Shipment validation result schema."""
    order_id: str
    tracking_number: Optional[str] = None
    tracking_url: Optional[str] = None
    carrier: Optional[str] = None
    validation_passed: bool
    validation_checks: Dict[str, bool]
    warnings: List[str]
    can_ship: bool

class ShipmentValidationResponse(BaseSchema):
    """Shipment validation response schema."""
    total_checked: int
    valid_for_shipment: int
    invalid_for_shipment: int
    results: List[ShipmentValidationResult]
    summary: Dict[str, Any]

class ShipmentConfirmRequest(BaseSchema):
    """Shipment confirm request schema."""
    order_ids: List[str]
    validate_only: bool = False
    force_confirm: bool = False

class ShipmentConfirmResult(BaseSchema):
    """Shipment confirm result schema."""
    order_id: str
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None

class ShipmentConfirmResponse(BaseSchema):
    """Shipment confirm response schema."""
    total_processed: int
    successful: int
    failed: int
    batch_id: Optional[str] = None
    results: List[ShipmentConfirmResult]

class BatchStatusResponse(BaseSchema):
    """Batch status response schema."""
    batch_id: str
    status: str
    total_orders: int
    processed_orders: int
    successful: int
    failed: int
    progress: float
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    shipments: List[Dict[str, Any]]

class ShipmentHistoryItem(BaseSchema):
    """Shipment history item schema."""
    id: int
    order_id: str
    commercial_id: Optional[str] = None
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None
    tracking_url: Optional[str] = None
    order_state: Optional[str] = None
    campaign_number: Optional[str] = None
    ean_code: Optional[str] = None
    shipment_confirmed: bool
    shipment_date: Optional[str] = None
    status: str
    error: Optional[str] = None

class ShipmentHistoryResponse(BaseSchema):
    """Shipment history response schema."""
    total: int
    page: int
    limit: int
    pages: int
    has_next: bool
    has_previous: bool
    items: List[ShipmentHistoryItem]
