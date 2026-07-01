from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.core.exceptions import NotFoundException
from app.core.response import ApiResponse
from app.schemas.tracking import BulkTrackingUpdateRequest
from app.services.tracking_service import TrackingService

router = APIRouter()

@router.get("/ready-orders")
async def get_ready_orders(
    # Removed start_date and end_date required parameters
    carrier_filter: Optional[str] = Query(None, description="Filter by carrier (e.g., 'Colissimo', 'GLS')"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get all orders ready for tracking update (no date filtering)
    Returns orders where:
    - Label has been generated
    - Tracking number exists
    - Tracking has NOT been updated yet in Mirakl
    - No errors present
    """
    service = TrackingService(db)
    result = await service.get_ready_orders(
        user_id=current_user.id,
        carrier_filter=carrier_filter,
        page=page,
        limit=limit
    )
    return ApiResponse(data=result)

@router.post("/bulk-update")
async def bulk_update_tracking(
    request: BulkTrackingUpdateRequest,
    background_tasks: BackgroundTasks,
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """Bulk update tracking numbers for selected orders with batch tracking"""
    service = TrackingService(db)
    result = await service.bulk_update(
        user_id=current_user.id,
        order_ids=request.order_ids,
        force_update=request.force_update
    )
    return ApiResponse(
        message=result["message"],
        data=result
    )

@router.post("/bulk-update-by-filter")
async def bulk_update_by_filter(
    background_tasks: BackgroundTasks,
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
    carrier_filter: Optional[str] = Query(None, description="Filter by carrier"),
    force_update: bool = Query(False, description="Force update even if errors"),
    max_orders: Optional[int] = Query(None, ge=1, le=500, description="Maximum number of orders to process")
):
    """
    Bulk update tracking for all eligible orders matching filter criteria
    (no date range required - processes all available orders)
    """
    service = TrackingService(db)

    # First get all eligible orders
    ready_orders = await service.get_ready_orders(
        user_id=current_user.id,
        carrier_filter=carrier_filter,
        page=1,
        limit=max_orders or 500  # Use max_orders as limit
    )

    # Extract order IDs from eligible orders
    order_ids = [order["order_id"] for order in ready_orders["items"] if order["can_update"]]

    if not order_ids:
        return ApiResponse(
            message="No eligible orders found for tracking update",
            data={"total_processed": 0}
        )

    # Apply max_orders limit
    if max_orders and len(order_ids) > max_orders:
        order_ids = order_ids[:max_orders]

    # Perform bulk update
    result = await service.bulk_update(
        user_id=current_user.id,
        order_ids=order_ids,
        force_update=force_update
    )

    return ApiResponse(
        message=f"Started tracking update for {len(order_ids)} orders",
        data=result
    )

@router.get("/batch/{batch_id}/status")
async def get_batch_status(
    batch_id: str,
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """Get status of a tracking batch"""
    service = TrackingService(db)
    status = service.get_batch_status(batch_id, current_user.id)
    if not status:
        raise NotFoundException("Batch not found")
    return ApiResponse(data=status)

@router.get("/batches")
async def get_batches(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """Get list of all tracking batches"""
    service = TrackingService(db)
    result = service.get_batches(current_user.id, page, limit)
    return ApiResponse(data=result)

@router.get("/status/{process_id}")
async def get_tracking_status(
    process_id: int,
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """Get tracking status for all orders in a process (legacy support)"""
    service = TrackingService(db)
    status = service.get_tracking_status(process_id, current_user.id)
    return ApiResponse(data=status)

__all__ = ["router"]
