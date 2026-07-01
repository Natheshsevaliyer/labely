from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import deps
from app.core.response import ApiResponse
from app.services.dashboard_service import DashboardService

router = APIRouter()

@router.get("/simple")
async def get_dashboard_simple(
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """Simple dashboard endpoint with all metrics"""
    service = DashboardService(db)
    data = await service.get_full_dashboard(current_user.id)
    return ApiResponse(data=data)
__all__ = ["router"]
