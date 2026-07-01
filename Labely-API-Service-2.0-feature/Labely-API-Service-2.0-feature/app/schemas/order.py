from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field, model_validator

from .base import BaseSchema


class GenerateLabelsRequest(BaseSchema):
    """Generate labels request schema with three options."""

    # SRP/Carrier name
    srp: str = Field(..., description="SRP/Carrier name (e.g., 'SRP', 'SRP_COLISSIMO')")

    # Option 1: Count-based (quantity)
    quantity: Optional[int] = Field(None, ge=1, le=100, description="Number of labels to generate")

    # Option 2: Date range-based
    start_date: Optional[str] = Field(None, description="Start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End date (YYYY-MM-DD)")

    # Option 3: Single order with multiple copies (NEW)
    order_id: Optional[str] = Field(None, description="Single order ID for multi-copy generation")
    label_count: Optional[int] = Field(None, ge=1, le=100, description="Number of label copies for single order")

    @model_validator(mode='after')
    def validate_request(self):
        """Validate that exactly one method is provided."""
        quantity_provided = self.quantity is not None
        date_range_provided = self.start_date is not None or self.end_date is not None
        multi_copy_provided = self.order_id is not None or self.label_count is not None

        # Count how many methods are provided
        methods_provided = sum([quantity_provided, date_range_provided, multi_copy_provided])

        # If none provided
        if methods_provided == 0:
            raise ValueError("Either 'quantity', date range, or 'order_id+label_count' must be provided")

        # If more than one provided
        if methods_provided > 1:
            raise ValueError("Cannot provide multiple methods. Choose one: quantity, date range, or order_id+label_count")

        # Validate multi-copy method
        if multi_copy_provided:
            if self.order_id is None or self.label_count is None:
                raise ValueError("Both 'order_id' and 'label_count' must be provided together")

            # Validate order_id format (optional: add regex if needed)
            if not self.order_id or len(self.order_id) < 3:
                raise ValueError("Valid order_id is required")

        # Validate date range method
        if date_range_provided:
            if self.start_date is None or self.end_date is None:
                raise ValueError("Both start_date and end_date must be provided together")

            # Validate date format
            try:
                start = datetime.strptime(self.start_date, "%Y-%m-%d")
                end = datetime.strptime(self.end_date, "%Y-%m-%d")

                if start > end:
                    raise ValueError("start_date must be before or equal to end_date")

            except ValueError as e:
                if "does not match format" in str(e):
                    raise ValueError("Invalid date format. Use YYYY-MM-DD")
                raise e

        return self

class GenerateLabelsResponse(BaseSchema):
    """Generate labels response schema."""
    success: bool
    message: str
    process_id: Optional[int] = None
    download_url: Optional[str] = None
    total_orders: int
    successful: int = 0
    failed: int = 0
    successful_orders: Optional[List[Dict[str, Any]]] = None
    failed_orders: Optional[List[Dict[str, Any]]] = None
    # Include request info for clarity
    request_method: str  # "quantity" or "date_range"
    requested_srp: str
    requested_quantity: Optional[int] = None
    requested_start_date: Optional[str] = None
    requested_end_date: Optional[str] = None

class ProcessStatusResponse(BaseSchema):
    """Process status response schema."""
    process_id: int
    status: str
    total: int
    successful: int
    failed: int
    download_url: Optional[str] = None
    labels_only_url: Optional[str] = None
    report_url: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    # Request info
    srp: str
    request_method: str
    requested_quantity: Optional[int] = None
    requested_start_date: Optional[str] = None
    requested_end_date: Optional[str] = None

class OrderInfo(BaseSchema):
    """Order information schema."""
    order_id: str
    order_date: str
    carrier_manager: Optional[str]
    order_state: str
    can_shop_ship: bool

class OrderFilterRequest(BaseSchema):
    """Order filter request schema."""
    srp: str
    order_state: str = "SHIPPING"
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = Field(100, ge=1, le=100)

class UnifiedSaleResponse(BaseSchema):
    sale_id: str
    sale_date: datetime
    carrier: str
    order_id: str
    status: str