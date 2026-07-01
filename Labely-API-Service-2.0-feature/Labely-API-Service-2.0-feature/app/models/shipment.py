
from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, Text

from app.models.base import BaseModel
from app.models.enums import ShipmentStatusEnum


class Shipment(BaseModel):
    __tablename__ = "shipments"

    user_id = Column(Integer, nullable=False, index=True)
    batch_id = Column(String(100), index=True)
    order_id = Column(String(100), nullable=False, unique=True)
    commercial_id = Column(String(100))
    process_id = Column(Integer)

    # Order details
    order_state = Column(String(50))
    order_date = Column(DateTime)
    campaign_number = Column(String(100))
    ean_code = Column(String(50))

    # Shipping details
    tracking_number = Column(String(100))
    carrier_used = Column(String(50))
    tracking_url = Column(String(500))

    # Shipment status
    shipment_confirmed = Column(Boolean, default=False)
    shipment_date = Column(DateTime)
    shipment_status = Column(Enum(ShipmentStatusEnum), default=ShipmentStatusEnum.PENDING)
    original_tracking_id = Column(Integer)

    # Error handling
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    completed_at = Column(DateTime)

class ShipmentBatch(BaseModel):
    __tablename__ = "shipment_batches"

    batch_id = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)

    # Batch stats
    total_orders = Column(Integer, default=0)
    processed_orders = Column(Integer, default=0)
    successful = Column(Integer, default=0)
    failed = Column(Integer, default=0)

    # Status
    status = Column(Enum(ShipmentStatusEnum), default=ShipmentStatusEnum.PENDING)

    # Date range
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    completed_at = Column(DateTime)
