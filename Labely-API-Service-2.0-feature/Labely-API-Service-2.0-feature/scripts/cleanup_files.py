#!/usr/bin/env python
"""Clean up old files."""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.services.file_service import file_service
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup():
    """Clean up old files."""
    try:
        logger.info(f"Cleaning up files older than {settings.FILE_CLEANUP_DAYS} days")
        file_service.cleanup_old_files(days_old=settings.FILE_CLEANUP_DAYS)
        logger.info("Cleanup completed")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    cleanup()