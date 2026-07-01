from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar('T')

class BaseSchema(BaseModel):
    """Base schema with common configuration."""
    model_config = ConfigDict(from_attributes=True)

class TimestampSchema(BaseSchema):
    """Schema with timestamp fields."""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class PaginationParams(BaseSchema):
    """Pagination parameters."""
    page: int = 1
    limit: int = 50

class PaginatedResponse(BaseSchema, Generic[T]):
    """Paginated response."""
    items: List[T]
    total: int
    page: int
    limit: int
    pages: int
    has_next: bool
    has_previous: bool
