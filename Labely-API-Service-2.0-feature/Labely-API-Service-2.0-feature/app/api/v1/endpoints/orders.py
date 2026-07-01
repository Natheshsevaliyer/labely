
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.api import deps
from app.core.response import ApiResponse
from app.schemas.order import GenerateLabelsRequest, GenerateLabelsResponse, ProcessStatusResponse
from app.services.mirakl.order_service import mirakl_order_service
from app.services.order_service import OrderService
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# app/api/v1/endpoints/orders.py - Add this new endpoint

# app/api/v1/endpoints/orders.py

@router.get("/mirakl-orders-status")
async def get_mirakl_orders_status(
    srp: str = Query(..., description="SRP/Carrier name (e.g., 'SRP', 'SRP_COLISSIMO')"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Fetch Mirakl orders with label generation status.
    Returns ALL SHIPPING state orders for the specified SRP with:
    - Order ID
    - Order date
    - Campaign number
    - Label generation count (how many times label was generated)
    - Order state (always SHIPPING)
    - Current status
    """
    try:
        service = OrderService(db)
        result = await service.get_mirakl_orders_with_status(
            user_id=current_user.id,
            srp=srp,
            page=page,
            limit=limit
        )
        return ApiResponse(data=result)
    except Exception as e:
        logger.error(f"Error fetching Mirakl orders for SRP={srp}: {str(e)}", exc_info=True)
        raise


@router.post("/generate-labels", response_model=ApiResponse[GenerateLabelsResponse])
async def generate_labels(
    request: GenerateLabelsRequest,
    background_tasks: BackgroundTasks,
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Generate labels for orders based on SRP and either:
    - Quantity: number of labels to generate (last 30 days)
    - Date range: all orders in specified date range
    - Order ID + Label count: multiple copies for a single order
    """
    service = OrderService(db)
    result = await service.generate_labels(
        user_id=current_user.id,
        srp=request.srp,
        quantity=request.quantity,
        start_date=request.start_date,
        end_date=request.end_date,
        order_id=request.order_id,      # ADD THIS
        label_count=request.label_count  # ADD THIS
    )

    return ApiResponse(
        success=result["success"],
        message=result["message"],
        data=GenerateLabelsResponse(**result)
    )

@router.get("/available-srps")
async def get_available_srps(
    days_back: int = Query(settings.MIRAKL_QUANTITY_FETCH_DAYS, description="Number of days to look back"),
    current_user = Depends(deps.get_current_user)
):
    """Get list of available SRPs from recent orders"""
    srps = await mirakl_order_service.get_available_srps(days_back)
    return ApiResponse(data={"srps": srps, "total": len(srps)})

@router.get("/process/{process_id}/status", response_model=ApiResponse[ProcessStatusResponse])
async def get_process_status(
    process_id: int,
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """Get real-time status of a label generation process"""
    service = OrderService(db)
    status = await service.get_process_status(process_id, current_user.id)
    return ApiResponse(data=ProcessStatusResponse(**status))
# --- ADD THIS TO THE BOTTOM OF app/api/v1/endpoints/orders.py ---

@router.get("/unified-sales", response_model=ApiResponse)
async def get_unified_sales_table(
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    service = OrderService(db)
    data = await service.get_unified_sales(user_id=current_user.id)
    return ApiResponse(data=data)


@router.get("/mirakl-test")
async def test_mirakl_connection(current_user = Depends(deps.get_current_user)):
    """Test endpoint to verify Mirakl connection and credentials"""
    try:
        # Test if mirakl_order_service is initialized
        logger.info(f"Mirakl Base URL: {settings.MIRAKL_BASE_URL}")
        logger.info(f"Mirakl Shop ID: {settings.MIRAKL_SHOP_ID}")
        
        # Try a simple test call with max=1
        test_orders = mirakl_order_service.fetch_orders_with_filters(
            carrier_manager="SRP",
            order_state="SHIPPING",
            max=1
        )
        
        return ApiResponse(
            success=True,
            data={
                "message": "Mirakl connection successful",
                "test_call_result": f"Retrieved {len(test_orders)} orders",
                "mirakl_base_url": settings.MIRAKL_BASE_URL,
                "mirakl_shop_id": settings.MIRAKL_SHOP_ID,
            }
        )
    except Exception as e:
        logger.error(f"Mirakl connection test failed: {str(e)}", exc_info=True)
        return ApiResponse(
            success=False,
            error=str(e),
            data={
                "message": "Mirakl connection failed",
                "error_details": str(e),
                "mirakl_base_url": settings.MIRAKL_BASE_URL,
            }
        )

__all__ = ["router"]
