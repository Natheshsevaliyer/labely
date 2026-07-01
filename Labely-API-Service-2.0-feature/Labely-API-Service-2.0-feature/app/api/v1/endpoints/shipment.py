from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.core.exceptions import NotFoundException
from app.core.response import ApiResponse
from app.schemas.shipment import (
    ShipmentConfirmRequest,
    ShipmentValidationRequest,
)
from app.services.shipment_service import ShipmentService

router = APIRouter()

@router.get("/ready-orders")
async def get_ready_shipments(
    carrier_filter: Optional[str] = Query(None, description="Filter by carrier (e.g., 'Colissimo', 'GLS')"),
    include_confirmed: bool = Query(False, description="Include already confirmed shipments"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get all orders ready for shipment confirmation (no date filtering)
    Returns orders where:
    - Label has been generated
    - Tracking number exists
    - Tracking has been updated in Mirakl
    - Shipment has NOT been confirmed yet
    """
    service = ShipmentService(db)
    result = await service.get_ready_shipments(
        user_id=current_user.id,
        carrier_filter=carrier_filter,
        include_confirmed=include_confirmed,
        page=page,
        limit=limit
    )
    return ApiResponse(data=result)

@router.post("/confirm")
async def confirm_shipments(
    request: ShipmentConfirmRequest,
    background_tasks: BackgroundTasks,
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Confirm shipment for specific orders (OR24)
    """
    service = ShipmentService(db)
    result = await service.confirm_shipments(
        user_id=current_user.id,
        order_ids=request.order_ids,
        validate_only=request.validate_only,
        force_confirm=request.force_confirm
    )
    return ApiResponse(data=result)

@router.post("/confirm-all")
async def confirm_all_ready_shipments(
    background_tasks: BackgroundTasks,
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
    carrier_filter: Optional[str] = Query(None, description="Filter by carrier"),
    force_confirm: bool = Query(False, description="Force confirmation even if validation fails"),
    max_orders: Optional[int] = Query(None, ge=1, le=500, description="Maximum number of orders to process")
):
    """
    Confirm ALL eligible shipments (no date range required)
    Processes all orders that are ready for shipment confirmation
    """
    service = ShipmentService(db)

    # First get all eligible orders
    ready_orders = await service.get_ready_shipments(
        user_id=current_user.id,
        carrier_filter=carrier_filter,
        include_confirmed=False,
        page=1,
        limit=max_orders or 500
    )

    # Filter orders that can be shipped
    order_ids = []
    skipped_details = []

    for shipment in ready_orders["items"]:
        if shipment["validation_passed"] or force_confirm:
            if not shipment["shipment_confirmed"]:
                order_ids.append(shipment["order_id"])
            else:
                skipped_details.append({
                    "order_id": shipment["order_id"],
                    "reason": "Already confirmed"
                })
        else:
            skipped_details.append({
                "order_id": shipment["order_id"],
                "reason": "Validation failed",
                "warnings": shipment.get("warnings", [])
            })

    if not order_ids:
        return ApiResponse(
            message="No eligible orders found for shipment confirmation",
            data={
                "total_eligible": len(ready_orders["items"]),
                "processed": 0,
                "skipped_details": skipped_details[:10]
            }
        )

    # Apply max_orders limit
    if max_orders and len(order_ids) > max_orders:
        order_ids = order_ids[:max_orders]

    # Create validation-only request
    validation_request = ShipmentConfirmRequest(
        order_ids=order_ids,
        validate_only=False,
        force_confirm=force_confirm
    )

    # Perform shipment confirmation
    result = await service.confirm_shipments(
        user_id=current_user.id,
        order_ids=order_ids,
        validate_only=False,
        force_confirm=force_confirm
    )

    result["total_eligible"] = len(ready_orders["items"])
    result["skipped_details"] = skipped_details[:10]

    return ApiResponse(
        message=f"Started shipment confirmation for {len(order_ids)} orders",
        data=result
    )

@router.post("/validate")
async def validate_shipments(
    request: ShipmentValidationRequest,
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Validate orders for shipment confirmation without actually confirming
    """
    service = ShipmentService(db)
    result = await service.validate_shipments(
        user_id=current_user.id,
        order_ids=request.order_ids,
        force_confirm=request.force_confirm
    )
    return ApiResponse(data=result)

@router.get("/batch/{batch_id}/status")
async def get_batch_status(
    batch_id: str,
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """Get status of a shipment batch"""
    service = ShipmentService(db)
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
    """Get list of all shipment batches"""
    service = ShipmentService(db)
    result = service.get_batches(current_user.id, page, limit)
    return ApiResponse(data=result)

@router.get("/history")
async def get_shipment_history(
    start_date: Optional[str] = Query(None, regex=r"^\d{4}-\d{2}-\d{2}$", description="Filter by start date (optional)"),
    end_date: Optional[str] = Query(None, regex=r"^\d{4}-\d{2}-\d{2}$", description="Filter by end date (optional)"),
    carrier_filter: Optional[str] = Query(None, description="Filter by carrier"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get shipment history with optional date filters
    If no dates provided, returns all history (paginated)
    """
    service = ShipmentService(db)
    result = service.get_history(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
        carrier_filter=carrier_filter,
        page=page,
        limit=limit
    )
    return ApiResponse(data=result)

__all__ = ["router"]
