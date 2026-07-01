"""Generic pagination helpers to eliminate copy-paste across services."""
from typing import Any, Dict, List, TypeVar

from sqlalchemy.orm import Query

T = TypeVar("T")


def paginate_query(query: Query, page: int, limit: int):
    """Apply OFFSET/LIMIT to a SQLAlchemy query and return (total, items)."""
    total = query.count()
    offset = (page - 1) * limit
    items = query.offset(offset).limit(limit).all()
    return total, items


def build_page_response(
    items: List[Any],
    total: int,
    page: int,
    limit: int,
    *,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a standardised paginated response envelope."""
    pages = (total + limit - 1) // limit if total > 0 else 0
    response: Dict[str, Any] = {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages,
        "has_next": page < pages,
        "has_previous": page > 1,
        "items": items,
    }
    if extra:
        response.update(extra)
    return response
