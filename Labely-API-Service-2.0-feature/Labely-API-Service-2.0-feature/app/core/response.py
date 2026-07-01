from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar('T')

class ApiResponse(BaseModel, Generic[T]):
    """Standard API response"""
    success: bool = True
    message: Optional[str] = None
    data: Optional[T] = None
    error: Optional[str] = None
    timestamp: datetime = datetime.utcnow()

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response"""
    items: List[T]
    total: int
    page: int
    limit: int
    pages: int
    has_next: bool
    has_previous: bool

class ErrorResponse(BaseModel):
    """Error response"""
    success: bool = False
    error: str
    message: Optional[str] = None
    details: Optional[Any] = None
    timestamp: str = datetime.utcnow().isoformat()  # Store as string, not datetime

    class Config:
        arbitrary_types_allowed = True
