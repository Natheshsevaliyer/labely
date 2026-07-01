"""Date utility functions."""
from datetime import datetime, timedelta
from typing import Optional, Tuple


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string to datetime."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None

def format_date(date: datetime, format: str = "%Y-%m-%d") -> str:
    """Format datetime to string."""
    return date.strftime(format)

def get_date_range(days_back: int) -> Tuple[str, str]:
    """Get date range for the last N days."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    return format_date(start_date), format_date(end_date)

def get_month_range(year: int, month: int) -> Tuple[datetime, datetime]:
    """Get start and end of month."""
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end
