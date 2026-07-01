"""File utility functions."""
import os
from datetime import datetime
from typing import Optional


def ensure_dir(path: str) -> str:
    """Ensure directory exists."""
    os.makedirs(path, exist_ok=True)
    return path

def safe_filename(filename: str) -> str:
    """Generate safe filename."""
    return "".join(c for c in filename if c.isalnum() or c in "._- ").rstrip()

def get_file_size(path: str) -> int:
    """Get file size in bytes."""
    return os.path.getsize(path) if os.path.exists(path) else 0

def cleanup_old_files(directory: str, days_old: int, pattern: Optional[str] = None):
    """Delete files older than specified days."""
    cutoff = datetime.now().timestamp() - (days_old * 86400)

    for filename in os.listdir(directory):
        if pattern and pattern not in filename:
            continue

        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath) and os.path.getmtime(filepath) < cutoff:
            os.remove(filepath)
