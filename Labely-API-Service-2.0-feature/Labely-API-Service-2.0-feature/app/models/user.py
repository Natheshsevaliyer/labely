
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.core.security import hash_password, verify_password
from app.models.base import BaseModel


class User(BaseModel):
    __tablename__ = "users"

    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)

    # Relationships
    processes = relationship("OrderProcess", back_populates="user", cascade="all, delete-orphan")
    tracking_updates = relationship("TrackingUpdate", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password: str):
        self.password = hash_password(password)

    def verify_password(self, password: str) -> bool:
        return verify_password(password, self.password)

class PasswordResetToken(BaseModel):
    __tablename__ = "password_reset_tokens"

    user_id = Column(Integer, nullable=False, index=True)
    token = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
