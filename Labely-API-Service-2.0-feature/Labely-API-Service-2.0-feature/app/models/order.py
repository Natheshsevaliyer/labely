from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class OrderProcess(BaseModel):
    __tablename__ = "order_processes"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    srp = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(50), default="Pending")
    total_orders = Column(Integer, default=0)
    successful_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    output_file = Column(String(500))
    output_url = Column(String(500))
    error_message = Column(Text)
    completed_at = Column(DateTime)

    # New fields for request method tracking
    request_method = Column(String(20), default="quantity")  # "quantity" or "date_range"
    requested_start_date = Column(DateTime, nullable=True)  # Store the requested start date
    requested_end_date = Column(DateTime, nullable=True)    # Store the requested end date

    # Relationships
    user = relationship("User", back_populates="processes")
    tracking_updates = relationship("TrackingUpdate", back_populates="process", cascade="all, delete-orphan")

class Order(BaseModel):
    __tablename__ = "orders"

    order_id = Column(String(100), unique=True, index=True, nullable=False)
    carrier_manager = Column(String(100), nullable=False)
    order_state = Column(String(50), nullable=False)
    order_date = Column(DateTime, nullable=False)
    customer_name = Column(String(200))
    customer_address = Column(String(500))

    # Relationships - Fix the foreign key reference
    # tracking_updates = relationship(
    #     "TrackingUpdate",
    #     primaryjoin="Order.order_id == TrackingUpdate.order_id",
    #     foreign_keys="[TrackingUpdate.order_id]",
    #     back_populates="order",
    #     overlaps="tracking_updates"
    # )
