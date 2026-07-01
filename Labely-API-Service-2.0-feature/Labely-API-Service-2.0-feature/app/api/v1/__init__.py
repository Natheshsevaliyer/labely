"""API v1 package."""
from fastapi import APIRouter

from .endpoints import (
    auth_router,
    dashboard_router,
    download_router,
    orders_router,
    shipment_router,
    sse_router,
    tracking_router,
)

router = APIRouter()

router.include_router(auth_router, prefix="/auth", tags=["authentication"])
router.include_router(orders_router, prefix="/orders", tags=["orders"])
router.include_router(tracking_router, prefix="/tracking", tags=["tracking"])
router.include_router(shipment_router, prefix="/shipment", tags=["shipment"])
router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
router.include_router(download_router, prefix="/download", tags=["download"])
router.include_router(sse_router, prefix="/sse", tags=["sse"])
