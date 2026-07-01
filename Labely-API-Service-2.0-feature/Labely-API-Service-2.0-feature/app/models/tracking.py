
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from app.models.enums import BatchStatusEnum, TrackingStatusEnum


class TrackingUpdate(BaseModel):
    __tablename__ = "tracking_updates"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(String(100), nullable=False, unique=True)
    commercial_id = Column(String(100))
    process_id = Column(Integer, ForeignKey("order_processes.id", ondelete="CASCADE"), nullable=False)
    batch_id = Column(String(100), ForeignKey("tracking_batches.batch_id", ondelete="SET NULL"), nullable=True)

    # Order details
    order_state = Column(String(50))
    order_date = Column(DateTime)
    campaign_number = Column(String(100))
    ean_code = Column(String(50))

    # Tracking details
    tracking_number = Column(String(100))
    carrier_used = Column(String(50))
    country = Column(String(10), nullable=True)
    label_generated = Column(Boolean, default=False)
    tracking_updated = Column(Boolean, default=False)
    shipment_confirmed = Column(Boolean, default=False)
    label_generated_count = Column(Integer, default=0)
    error_message = Column(Text)
    status = Column(Enum(TrackingStatusEnum), default=TrackingStatusEnum.NOT_YET)
    update_attempts = Column(Integer, default=0)
    last_attempt = Column(DateTime)

    # Relationships
    user = relationship("User", back_populates="tracking_updates")
    process = relationship("OrderProcess", back_populates="tracking_updates")
    batch = relationship("TrackingBatch", back_populates="tracking_updates")

class TrackingBatch(BaseModel):
    __tablename__ = "tracking_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)

    # Batch stats
    total_orders = Column(Integer, default=0)
    processed_orders = Column(Integer, default=0)
    successful = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    already_updated = Column(Integer, default=0)

    # Status
    status = Column(Enum(BatchStatusEnum), default=BatchStatusEnum.PENDING)

    # Filters used for this batch (now truly optional)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    carrier_filter = Column(String(50), nullable=True)
    force_update = Column(Boolean, default=False)

    # Timestamps
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    tracking_updates = relationship("TrackingUpdate", back_populates="batch", cascade="all, delete-orphan")
