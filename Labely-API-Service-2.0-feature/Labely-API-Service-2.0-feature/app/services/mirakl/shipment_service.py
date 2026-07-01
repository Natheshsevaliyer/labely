import logging
from typing import Any, Dict

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

class MiraklShipmentService:
    """Mirakl Shipment Confirmation operations"""

    def __init__(self):
        self.base_url = settings.MIRAKL_BASE_URL
        self.api_key = settings.MIRAKL_API_KEY
        self.shop_id = settings.MIRAKL_SHOP_ID
        self.headers = {
            "Authorization": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def validate_tracking_for_shipment(self, order_id: str, tracking_number: str, tracking_url: str) -> Dict[str, Any]:
        """Validate tracking meets Showroomprive requirements"""
        result = {"valid": True, "checks": {}, "warnings": []}

        # Check tracking ID exists
        check1 = bool(tracking_number and tracking_number.strip())
        result["checks"]["has_tracking_id"] = check1
        if not check1:
            result["valid"] = False
            result["warnings"].append("Missing tracking number")

        # Check URL contains http
        check2 = tracking_url and ("http://" in tracking_url.lower() or "https://" in tracking_url.lower())
        result["checks"]["has_valid_url"] = check2
        if not check2:
            result["valid"] = False
            result["warnings"].append("URL must contain http:// or https://")

        # Check URL is not generic
        generic_urls = ["laposte.fr", "gls-group.com", "colissimo.fr"]
        if tracking_url:
            if any(domain in tracking_url.lower() for domain in generic_urls):
                if "?" not in tracking_url and "=" not in tracking_url:
                    result["checks"]["is_specific_url"] = False
                    result["warnings"].append("URL appears generic")

        return result

    def confirm_shipment(self, order_id: str) -> Dict[str, Any]:
        """OR24 - Confirm shipment for an order"""
        url = f"{self.base_url}/api/orders/{order_id}/ship"
        params = {"shop_id": self.shop_id}

        try:
            logger.info(f"Confirming shipment for {order_id}")
            response = requests.put(url, headers=self.headers, params=params, timeout=30)

            if response.status_code == 204:
                return {
                    "success": True,
                    "order_id": order_id,
                    "message": "Shipment confirmed successfully"
                }

            error_detail = f"HTTP {response.status_code}"
            try:
                if response.content:
                    error_detail = response.json()
            except Exception:
                error_detail = response.text or str(response.status_code)

            logger.error(f"Failed to confirm shipment: {error_detail}")
            return {
                "success": False,
                "order_id": order_id,
                "error": error_detail
            }
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return {
                "success": False,
                "order_id": order_id,
                "error": str(e)
            }

mirakl_shipment_service = MiraklShipmentService()
