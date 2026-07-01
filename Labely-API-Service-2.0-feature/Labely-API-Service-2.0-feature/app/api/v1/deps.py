"""API v1 specific dependencies."""
from fastapi import Query

from app.core.exceptions import ValidationException


def validate_date_range(
    start_date: str = Query(..., regex=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: str = Query(..., regex=r"^\d{4}-\d{2}-\d{2}$"),
) -> tuple[str, str]:
    """Validate date range parameters."""
    if start_date > end_date:
        raise ValidationException("start_date must be before or equal to end_date")
    return start_date, end_date

def pagination_params(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
) -> dict:
    """Get pagination parameters."""
    return {"page": page, "limit": limit}
