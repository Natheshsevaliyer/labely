#!/usr/bin/env python
"""Fix process status for completed processes."""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models import OrderProcess, TrackingUpdate
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_process_status():
    """Update status for completed processes."""
    db = SessionLocal()
    try:
        # Find all processes stuck in "Processing" status
        processes = db.query(OrderProcess).filter(
            OrderProcess.status == "Processing"
        ).all()
        
        logger.info(f"Found {len(processes)} processes stuck in Processing status")
        
        for process in processes:
            # Check if all orders are processed
            tracking_records = db.query(TrackingUpdate).filter(
                TrackingUpdate.process_id == process.id
            ).all()
            
            if len(tracking_records) >= process.total_orders:
                successful = sum(1 for t in tracking_records if t.label_generated)
                failed = len(tracking_records) - successful
                
                if successful == process.total_orders:
                    process.status = "Completed"
                    logger.info(f"Process {process.id}: Completed (all {successful} orders successful)")
                elif successful > 0:
                    process.status = "Partial"
                    logger.info(f"Process {process.id}: Partial ({successful} successful, {failed} failed)")
                else:
                    process.status = "Failed"
                    logger.info(f"Process {process.id}: Failed (all {failed} orders failed)")
                
                process.completed_at = tracking_records[-1].updated_at if tracking_records else None
                process.successful_count = successful
                process.failed_count = failed
        
        db.commit()
        logger.info("Process status updated successfully")
        
    except Exception as e:
        logger.error(f"Error fixing process status: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_process_status()