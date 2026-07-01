"""Endpoints package."""
from .auth import router as auth_router
from .dashboard import router as dashboard_router
from .download import router as download_router
from .orders import router as orders_router
from .shipment import router as shipment_router
from .sse import router as sse_router
from .tracking import router as tracking_router

__all__ = [
    'auth_router',
    'orders_router',
    'tracking_router',
    'shipment_router',
    'dashboard_router',
    'download_router',
    'sse_router'

]
